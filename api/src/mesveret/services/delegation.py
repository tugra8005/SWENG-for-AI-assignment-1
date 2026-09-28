"""Havale: verme, yenileme, geri alma, süre dolumu, döngü kontrolü (R4) ve Karar Saati
penceresindeki kilit.

Her havale verildiği ya da yenilendiği anda ``havale_suresi`` kadar sonrasına bir bitiş anı alır.
Madde sonradan değişirse mevcut havalelerin bitişi değişmez. Bitişi geçen havale yürürlükten
kalkar: okumalar o ana göre süzülür, zamanlayıcı da vade anında havaleyi graftan siler ve deftere
``HAVALE_SURESI_DOLDU`` yazar. Karar Saati anlık görüntüsü açılış anındaki havaleleri alır; pencere
sırasında süresi dolan havale o oturum için geçerli kalır.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import DecisionSession, User
from mesveret.domain.delegation import (
    DelegationCycleError,
    DelegationEdge,
    SelfDelegationError,
    check_new_delegation,
    resolve_terminal,
)
from mesveret.errors import Conflict, DomainError, NotFound
from mesveret.services import interactions, ledger, ontology
from mesveret.services.profile import find_user, nickname_map

LOCK_MESSAGE = (
    "Karar Saati penceresi açık: havale grafı bu oturum için kilitli. "
    "Havaleyi pencere kapandıktan sonra değiştirebilirsiniz."
)


def window_open(ctx: Ctx) -> bool:
    return ctx.db.execute(
        select(DecisionSession.id).where(DecisionSession.status == "OPEN")
    ).first() is not None


def _check_area(ctx: Ctx, area_id: str | None) -> None:
    if area_id is not None and ctx.graph.area(area_id) is None:
        raise NotFound("Alan bulunamadı.")


def set_delegation(ctx: Ctx, user: User, target_nickname: str, area_id: str | None) -> None:
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    _check_area(ctx, area_id)
    target = find_user(ctx, target_nickname)
    delegations = ctx.graph.delegations(active_at=ctx.now)
    try:
        check_new_delegation(delegations, user.id, target.id, area_id, ctx.graph)
    except SelfDelegationError as exc:
        raise DomainError(str(exc)) from exc
    except DelegationCycleError as exc:
        names = nicknames(ctx, exc.path)
        raise DomainError(
            f"R4: Bu havale döngü oluşturur — {ontology.area_name(ctx, exc.area_id)} alanında "
            f"zincir size geri dönüyor ({' → '.join(names)})."
        ) from exc
    expires_at = ctx.now + ctx.reg.duration("havale_suresi")
    ctx.graph.set_delegation(user.id, target.id, area_id, ctx.now, expires_at)
    interactions.on_delegation(ctx, user.id, target.id)
    ledger.enqueue(ctx, "HAVALE_VERILDI", {
        "veren": user.nickname, "alan": target.nickname, "alan_id": area_id,
        "bitis": expires_at.isoformat(),
    })


def _own_edge(ctx: Ctx, user: User, area_id: str | None) -> DelegationEdge | None:
    return next((e for e in ctx.graph.outgoing_delegations(user.id, active_at=ctx.now)
                 if e.area_id == area_id), None)


def renew_delegation(ctx: Ctx, user: User, area_id: str | None) -> datetime:
    """Süreyi baştan başlatır: yeni bitiş şimdiden itibaren yürürlükteki ``havale_suresi``."""
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    edge = _own_edge(ctx, user, area_id)
    if edge is None:
        raise NotFound("Bu alanda yürürlükte bir havaleniz yok.")
    expires_at = ctx.now + ctx.reg.duration("havale_suresi")
    ctx.graph.renew_delegation(user.id, area_id, expires_at)
    ledger.enqueue(ctx, "HAVALE_YENILENDI", {
        "veren": user.nickname, "alan": nicknames(ctx, [edge.target_id])[0], "alan_id": area_id,
        "onceki_bitis": edge.expires_at.isoformat() if edge.expires_at else None,
        "bitis": expires_at.isoformat(),
    })
    return expires_at


def next_expiry(ctx: Ctx, until: datetime) -> DelegationEdge | None:
    """Bitişi ``until`` anına kadar gelen ilk havale (zamanlayıcı için)."""
    due = [e for e in ctx.graph.delegation_edges() if e.expires_at and e.expires_at <= until]
    return min(due, key=lambda e: (e.expires_at, e.user_id, e.area_id or ""), default=None)


def expire(ctx: Ctx, user_id: str, area_id: str | None) -> bool:
    """Vadesi gelen havaleyi graftan siler ve deftere yazar. Havale arada yenilendiyse dokunmaz."""
    edge = next((e for e in ctx.graph.outgoing_delegations(user_id)
                 if e.area_id == area_id), None)
    if edge is None or edge.expires_at is None or edge.expires_at > ctx.now:
        return False
    ctx.graph.remove_delegation(user_id, area_id)
    giver, target = nicknames(ctx, [user_id, edge.target_id])
    ledger.enqueue(ctx, "HAVALE_SURESI_DOLDU", {
        "veren": giver, "alan": target, "alan_id": area_id,
        "verildi": edge.since.isoformat(), "bitis": edge.expires_at.isoformat(),
        "not": "Oy sahibine döndü.",
    })
    return True


def revoke_delegation(ctx: Ctx, user: User, area_id: str | None) -> None:
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    if not ctx.graph.remove_delegation(user.id, area_id):
        raise NotFound("Bu alanda verilmiş bir havaleniz yok.")
    ledger.enqueue(ctx, "HAVALE_GERI_ALINDI", {"veren": user.nickname, "alan_id": area_id})


def nicknames(ctx: Ctx, ids: list[str]) -> list[str]:
    names = nickname_map(ctx, ids)
    return [names.get(i, i) for i in ids]


def _expiry_view(ctx: Ctx, e: DelegationEdge) -> dict:
    left = (e.expires_at - ctx.now) if e.expires_at else None
    return {
        "since": e.since,
        "expires_at": e.expires_at,
        "days_left": max(0, left.days + (1 if left.seconds or left.microseconds else 0)) if left else None,
        # Uyarı şeridi (bildirim sistemi yok): süresi havale_uyari_suresi içinde dolacaklar.
        "expiring": left is not None and left <= ctx.reg.duration("havale_uyari_suresi"),
    }


def my_delegations(ctx: Ctx, user: User) -> dict:
    """Verilen havaleler (zincirin nerede bittiği ve bitişiyle), alınan havaleler (verenleri ve
    bitişleriyle) ve süresi yakında dolacakların uyarısı."""
    delegations = ctx.graph.delegations(active_at=ctx.now)
    given = []
    for e in ctx.graph.outgoing_delegations(user.id, active_at=ctx.now):
        terminal, path = resolve_terminal(delegations, user.id, e.area_id, ctx.graph)
        given.append({
            "area_id": e.area_id,
            "area_name": ontology.area_name(ctx, e.area_id),
            "target": nicknames(ctx, [e.target_id])[0],
            "chain": nicknames(ctx, path),
            "terminal": nicknames(ctx, [terminal])[0],
            **_expiry_view(ctx, e),
        })
    incoming = [e for e in ctx.graph.delegation_edges(active_at=ctx.now) if e.target_id == user.id]
    names = nickname_map(ctx, [e.user_id for e in incoming])
    received_list = sorted(
        ({"from": names.get(e.user_id, e.user_id), "area_id": e.area_id,
          "area_name": ontology.area_name(ctx, e.area_id), **_expiry_view(ctx, e)}
         for e in incoming),
        key=lambda r: (r["expires_at"] is None, r["expires_at"] or ctx.now, r["from"]),
    )
    received = ctx.graph.incoming_delegations(user.id, active_at=ctx.now)
    return {
        "given": given,
        "received": [
            {"area_id": a, "area_name": ontology.area_name(ctx, a), "count": n}
            for a, n in sorted(received.items(), key=lambda kv: (kv[0] is not None, kv[0] or ""))
        ],
        "received_list": received_list,
        "expiring_given": [g for g in given if g["expiring"]],
        "expiring_received": [r for r in received_list if r["expiring"]],
        "warning_days": ctx.reg.duration("havale_uyari_suresi").days,
        "havale_suresi_gun": ctx.reg.duration("havale_suresi").days,
        "locked": window_open(ctx),
    }
