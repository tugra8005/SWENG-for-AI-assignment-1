"""Havale: istek ve kabul, yenileme, geri alma, iade, süre dolumu, döngü kontrolü (R4) ve Karar
Saati penceresindeki kilit.

Havale verildiğinde BEKLIYOR durumunda bir istek olarak başlar (``DelegationRequest``) ve grafa
girmez. Alan kişi kabul edince graf kenarı olur; ağırlık, zincir çözümlemesi ve Karar Saati anlık
görüntüsü yalnızca graf kenarlarını okuduğu için bekleyen havale yapısı gereği hiçbir oya katılmaz
ve oy verende kalır. Kabul edilmeyen istek ``havale_kabul_suresi`` sonunda düşer.

Böylece kimse bir yurttaşın gizli oyunu, pencereden hemen önce ona havale vererek açığa çıkaramaz:
oyun açık olması (ağırlığın 1'i aşması) alan kişinin en az bir havaleyi kabul etmesini gerektirir.
Kabul edilmiş havaleye zincirle akan havaleler ayrıca onay istemez.

Kabul anında ``havale_suresi`` kadar sonrasına bir bitiş anı alınır; yenileme süreyi baştan başlatır
ve yeniden kabul gerektirmez. Madde sonradan değişirse mevcut havalelerin bitişi değişmez. Bitişi
geçen havale yürürlükten kalkar: okumalar o ana göre süzülür, zamanlayıcı da vade anında havaleyi
graftan siler ve deftere ``HAVALE_SURESI_DOLDU`` yazar. Karar Saati anlık görüntüsü açılış
anındaki havaleleri alır; pencere sırasında süresi dolan havale o oturum için geçerli kalır.

Hâtif giriş yapamaz; ona verilen havale kural gereği hemen kabul edilir. Hâtif'in oyu her zaman
açık olduğu için bu gizlilik açısından bir şey değiştirmez.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import DecisionSession, DelegationRequest, User
from mesveret.domain.delegation import (
    DelegationCycleError,
    DelegationEdge,
    SelfDelegationError,
    check_new_delegation,
    resolve_terminal,
)
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import interactions, ledger, ontology
from mesveret.services.profile import find_user, nickname_map

LOCK_MESSAGE = (
    "Karar Saati penceresi açık: havale grafı bu oturum için kilitli. "
    "Havaleyi pencere kapandıktan sonra değiştirebilirsiniz."
)
PENDING = "PENDING"
OUTCOME_LABELS = {
    "REJECTED": "reddedildi",
    "EXPIRED": "kabul süresi doldu",
    "RETURNED": "iade edildi",
}


def window_open(ctx: Ctx) -> bool:
    return ctx.db.execute(
        select(DecisionSession.id).where(DecisionSession.status == "OPEN")
    ).first() is not None


def _check_area(ctx: Ctx, area_id: str | None) -> None:
    if area_id is not None and ctx.graph.area(area_id) is None:
        raise NotFound("Alan bulunamadı.")


def _check_cycle(ctx: Ctx, giver_id: str, target_id: str, area_id: str | None,
                 *, accepting: bool = False) -> None:
    try:
        check_new_delegation(ctx.graph.delegations(active_at=ctx.now), giver_id, target_id,
                             area_id, ctx.graph)
    except SelfDelegationError as exc:
        raise DomainError(str(exc)) from exc
    except DelegationCycleError as exc:
        names = nicknames(ctx, exc.path)
        where = f"{ontology.area_name(ctx, exc.area_id)} alanında"
        chain = " → ".join(names)
        raise DomainError(
            f"R4: Bu havaleyi kabul etmek döngü oluşturur — {where} zincir {names[0]} adlı "
            f"yurttaşa geri dönüyor ({chain}). Havaleyi reddedebilirsiniz."
            if accepting else
            f"R4: Bu havale döngü oluşturur — {where} zincir size geri dönüyor ({chain})."
        ) from exc


def _is_oracle(user: User) -> bool:
    from mesveret.services.oracle import ORACLE_ID  # oracle bu modülü dolaylı içe aktarır

    return user.id == ORACLE_ID


def _pending(ctx: Ctx, **filters) -> list[DelegationRequest]:
    q = select(DelegationRequest).where(DelegationRequest.status == PENDING,
                                        DelegationRequest.decide_by > ctx.now)
    for key, value in filters.items():
        q = q.where(getattr(DelegationRequest, key) == value)
    return list(ctx.db.execute(q.order_by(DelegationRequest.id)).scalars())


def _accepted_row(ctx: Ctx, giver_id: str, area_id: str | None) -> DelegationRequest | None:
    q = select(DelegationRequest).where(
        DelegationRequest.giver_id == giver_id, DelegationRequest.status == "ACCEPTED",
        DelegationRequest.area_id.is_(None) if area_id is None
        else DelegationRequest.area_id == area_id)
    return ctx.db.execute(q.order_by(DelegationRequest.id.desc())).scalars().first()


def _close(row: DelegationRequest | None, status: str, at: datetime) -> None:
    if row is not None:
        row.status, row.decided_at = status, at


def request_delegation(ctx: Ctx, user: User, target_nickname: str,
                       area_id: str | None) -> DelegationRequest:
    """Havale ver: alan kişi kabul edene kadar bekler (Hâtif'e verilen hemen kabul edilir).

    Aynı alanda bekleyen eski istek yenisiyle değişir. Kabul edilmiş bir havale varsa yenisi kabul
    edilene kadar o yürürlükte kalır."""
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    _check_area(ctx, area_id)
    target = find_user(ctx, target_nickname)
    if target.id == user.id:
        raise DomainError(str(SelfDelegationError()))
    if target.refuses_delegations:
        raise DomainError(f"{target.nickname} havale kabul etmiyor.")
    current = _own_edge(ctx, user, area_id)
    if current is not None and current.target_id == target.id:
        raise Conflict(f"Bu alandaki havaleniz zaten {target.nickname} adlı yurttaşta; süresini "
                       "yenilemek için Yenile'yi kullanın.")
    _check_cycle(ctx, user.id, target.id, area_id)
    for old in _pending(ctx, giver_id=user.id, area_id=area_id):
        _close(old, "CANCELLED", ctx.now)
    row = DelegationRequest(giver_id=user.id, target_id=target.id, area_id=area_id, status=PENDING,
                            created_at=ctx.now,
                            decide_by=ctx.now + ctx.reg.duration("havale_kabul_suresi"))
    ctx.db.add(row)
    ctx.db.flush()
    ledger.enqueue(ctx, "HAVALE_BEKLIYOR", {
        "veren": user.nickname, "alan": target.nickname, "alan_id": area_id,
        "son_kabul": row.decide_by.isoformat(),
    })
    if _is_oracle(target):
        _accept(ctx, row, target)
    return row


def _request_for_target(ctx: Ctx, user: User, request_id: int) -> DelegationRequest:
    row = ctx.db.get(DelegationRequest, request_id)
    if row is None or row.target_id != user.id:
        raise NotFound("Size verilmiş böyle bir havale yok.")
    if row.status != PENDING:
        raise Conflict("Bu havale artık beklemiyor.")
    if row.decide_by <= ctx.now:
        expire_request(ctx, row.id)
        raise Conflict("Bu havalenin kabul süresi doldu.")
    return row


def accept_request(ctx: Ctx, user: User, request_id: int) -> datetime:
    """Kabul: havale grafa girer, süresi şimdi başlar. Aynı alandaki eski havalenin yerini alır."""
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    row = _request_for_target(ctx, user, request_id)
    # Beklerken graf değişmiş olabilir: döngü kabul anında yeniden denetlenir.
    _check_cycle(ctx, row.giver_id, row.target_id, row.area_id, accepting=True)
    return _accept(ctx, row, user)


def _accept(ctx: Ctx, row: DelegationRequest, target: User) -> datetime:
    _close(_accepted_row(ctx, row.giver_id, row.area_id), "ENDED", ctx.now)
    expires_at = ctx.now + ctx.reg.duration("havale_suresi")
    ctx.graph.set_delegation(row.giver_id, row.target_id, row.area_id, ctx.now, expires_at)
    _close(row, "ACCEPTED", ctx.now)
    interactions.on_delegation(ctx, row.giver_id, row.target_id)
    ledger.enqueue(ctx, "HAVALE_KABUL", {
        "veren": nicknames(ctx, [row.giver_id])[0], "alan": target.nickname,
        "alan_id": row.area_id, "bitis": expires_at.isoformat(),
    })
    return expires_at


def reject_request(ctx: Ctx, user: User, request_id: int) -> None:
    """Ret: istek düşer, veren kendi Havale sayfasında "reddedildi" görür. Grafa dokunmadığı için
    pencere açıkken de yapılabilir."""
    row = _request_for_target(ctx, user, request_id)
    _close(row, "REJECTED", ctx.now)
    ledger.enqueue(ctx, "HAVALE_RED", {
        "veren": nicknames(ctx, [row.giver_id])[0], "alan": user.nickname,
        "alan_id": row.area_id, "neden": "reddedildi",
    })


def cancel_request(ctx: Ctx, user: User, request_id: int) -> None:
    """Veren bekleyen isteğini geri alır (grafa dokunmaz)."""
    row = ctx.db.get(DelegationRequest, request_id)
    if row is None or row.giver_id != user.id or row.status != PENDING:
        raise NotFound("Bekleyen böyle bir havaleniz yok.")
    _close(row, "CANCELLED", ctx.now)
    ledger.enqueue(ctx, "HAVALE_GERI_ALINDI", {
        "veren": user.nickname, "alan": nicknames(ctx, [row.target_id])[0],
        "alan_id": row.area_id, "bekleyen": True,
    })


def next_request_expiry(ctx: Ctx, until: datetime) -> DelegationRequest | None:
    """Kabul süresi ``until`` anına kadar dolan ilk bekleyen istek (zamanlayıcı için)."""
    return ctx.db.execute(
        select(DelegationRequest).where(DelegationRequest.status == PENDING,
                                        DelegationRequest.decide_by <= until)
        .order_by(DelegationRequest.decide_by, DelegationRequest.id).limit(1)
    ).scalar_one_or_none()


def expire_request(ctx: Ctx, request_id: int) -> bool:
    row = ctx.db.get(DelegationRequest, request_id)
    if row is None or row.status != PENDING or row.decide_by > ctx.now:
        return False
    _close(row, "EXPIRED", row.decide_by)
    giver, target = nicknames(ctx, [row.giver_id, row.target_id])
    ledger.enqueue(ctx, "HAVALE_RED", {
        "veren": giver, "alan": target, "alan_id": row.area_id, "neden": "kabul_suresi_doldu",
    })
    return True


def return_delegation(ctx: Ctx, user: User, giver_nickname: str, area_id: str | None) -> None:
    """İade: alan kişi kabul ettiği havaleyi istediği zaman geri çevirir (pencere açıkken kilitli).
    Oy verene döner."""
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    giver = find_user(ctx, giver_nickname)
    edge = _own_edge(ctx, giver, area_id)
    if edge is None or edge.target_id != user.id:
        raise NotFound("Bu yurttaştan bu alanda size verilmiş bir havale yok.")
    ctx.graph.remove_delegation(giver.id, area_id)
    _close(_accepted_row(ctx, giver.id, area_id), "RETURNED", ctx.now)
    ledger.enqueue(ctx, "HAVALE_IADE", {
        "veren": giver.nickname, "alan": user.nickname, "alan_id": area_id,
        "not": "Oy sahibine döndü.",
    })


def set_refusal(ctx: Ctx, user: User, refuses: bool) -> None:
    """"Havale kabul etmiyorum": açıksa yeni havale verilemez. Bekleyen ve kabul edilmiş havaleler
    kendiliğinden düşmez; kişi onları reddeder ya da iade eder."""
    if _is_oracle(user):
        raise Forbidden("Hâtif'in havale tercihi değiştirilemez.")
    user.refuses_delegations = refuses


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
    _close(_accepted_row(ctx, user_id, area_id), "ENDED", ctx.now)
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
    _close(_accepted_row(ctx, user.id, area_id), "ENDED", ctx.now)
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


def _requests_view(ctx: Ctx, user: User) -> dict:
    """Bekleyen istekler (verdiklerim ve bana verilenler) ve verdiğim havalelerin son sonucu:
    her alan için en son istek reddedildiyse, kabul süresi dolduysa ya da iade edildiyse."""
    given = _pending(ctx, giver_id=user.id)
    received = _pending(ctx, target_id=user.id)
    mine = ctx.db.execute(
        select(DelegationRequest).where(DelegationRequest.giver_id == user.id)
        .order_by(DelegationRequest.id.desc())
    ).scalars().all()
    latest: dict[str | None, DelegationRequest] = {}
    for r in mine:
        latest.setdefault(r.area_id, r)
    outcomes = [r for r in latest.values() if r.status in OUTCOME_LABELS]
    names = nickname_map(ctx, [r.target_id for r in (*given, *outcomes)]
                         + [r.giver_id for r in received])

    def base(r: DelegationRequest) -> dict:
        return {"id": r.id, "area_id": r.area_id, "area_name": ontology.area_name(ctx, r.area_id),
                "created_at": r.created_at}

    return {
        "pending_given": [{**base(r), "target": names.get(r.target_id), "decide_by": r.decide_by}
                          for r in given],
        "pending_received": [{**base(r), "from": names.get(r.giver_id), "decide_by": r.decide_by}
                             for r in received],
        "outcomes": sorted(
            ({**base(r), "target": names.get(r.target_id), "status": r.status,
              "label": OUTCOME_LABELS[r.status], "at": r.decided_at} for r in outcomes),
            key=lambda o: o["at"], reverse=True),
        "refuses": user.refuses_delegations,
        "kabul_suresi_gun": ctx.reg.duration("havale_kabul_suresi").days,
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
        **_requests_view(ctx, user),
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
