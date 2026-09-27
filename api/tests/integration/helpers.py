from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import Proposal, Topic, User
from mesveret.services import auth, proposals, scheduler, topics
from mesveret.services.proposals import ProposalInput


def headers_for(ctx: Ctx, user: User) -> dict:
    return {"Authorization": f"Bearer {auth.create_token(ctx.settings, user.id)}"}


def advance(ctx: Ctx, delta: timedelta) -> Ctx:
    """Sahte saati ilerletir ve aradaki işleri işler; yeni anın bağlamını döner."""
    target = clock.now(ctx.db) + delta
    clock.set_now(ctx.db, target)
    ctx.db.commit()
    later = ctx.at(target)
    scheduler.tick(later, target)
    return later


def open_topic(ctx: Ctx, user: User, title: str = "Film günleri", *, area: str = "sinema",
               scope: str = "genel", body: str = "Her ay bir film izleyelim.") -> Topic:
    """Bir KONU önerisi açar ve sessiz onayla kabul ettirir; oluşan konuyu döner."""
    p = proposals.open_proposal(ctx, user, ProposalInput(
        type="KONU", title=title, body=body, area_id=area, scope_id=scope,
    ))
    proposals.accept(ctx.at(p.deadline_at), p)
    ctx.db.commit()
    return ctx.db.execute(select(Topic).where(Topic.accepted_proposal_id == p.id)).scalar_one()


def post(ctx: Ctx, user: User, topic: Topic, text: str, reply_to: int | None = None):
    return topics.post_message(ctx, user, topic.id, text, reply_to)


def reload(ctx: Ctx, p: Proposal) -> Proposal:
    ctx.db.expire_all()
    return ctx.db.get(Proposal, p.id)


def mature(ctx: Ctx, p: Proposal, days: int = 8) -> Proposal:
    """Karar Saati testleri için: öneriyi olgunlaşmış olacak kadar geriye tarihler."""
    p.created_at = p.created_at - timedelta(days=days)
    if p.queued_at is not None:
        p.queued_at = p.queued_at - timedelta(days=days)
    ctx.db.commit()
    return p
