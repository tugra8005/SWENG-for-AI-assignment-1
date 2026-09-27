"""Havale: verme, geri alma, döngü kontrolü (R4) ve Karar Saati penceresindeki kilit."""

from __future__ import annotations

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import DecisionSession, User
from mesveret.domain.delegation import (
    DelegationCycleError,
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
    delegations = ctx.graph.delegations()
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
    ctx.graph.set_delegation(user.id, target.id, area_id, ctx.now)
    interactions.on_delegation(ctx, user.id, target.id)
    ledger.enqueue(ctx, "HAVALE_VERILDI", {
        "veren": user.nickname, "alan": target.nickname, "alan_id": area_id,
    })


def revoke_delegation(ctx: Ctx, user: User, area_id: str | None) -> None:
    if window_open(ctx):
        raise Conflict(LOCK_MESSAGE)
    if not ctx.graph.remove_delegation(user.id, area_id):
        raise NotFound("Bu alanda verilmiş bir havaleniz yok.")
    ledger.enqueue(ctx, "HAVALE_GERI_ALINDI", {"veren": user.nickname, "alan_id": area_id})


def nicknames(ctx: Ctx, ids: list[str]) -> list[str]:
    names = nickname_map(ctx, ids)
    return [names.get(i, i) for i in ids]


def my_delegations(ctx: Ctx, user: User) -> dict:
    """Verilen havaleler (zincirin nerede bittiğiyle) ve alınan havale sayıları."""
    delegations = ctx.graph.delegations()
    given = []
    for area, target, since in ctx.graph.outgoing_delegations(user.id):
        terminal, path = resolve_terminal(delegations, user.id, area, ctx.graph)
        given.append({
            "area_id": area,
            "area_name": ontology.area_name(ctx, area),
            "target": nicknames(ctx, [target])[0],
            "chain": nicknames(ctx, path),
            "terminal": nicknames(ctx, [terminal])[0],
            "since": since,
        })
    received = ctx.graph.incoming_delegations(user.id)
    return {
        "given": given,
        "received": [
            {"area_id": a, "area_name": ontology.area_name(ctx, a), "count": n}
            for a, n in sorted(received.items(), key=lambda kv: (kv[0] is not None, kv[0] or ""))
        ],
        "locked": window_open(ctx),
    }
