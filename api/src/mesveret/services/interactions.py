"""ETKILESIM grafı: sinyallerden türetilen ilişki ağırlıkları (baskın tespiti için).

Ağırlıklar ve zaman pencereleri ``etkilesim_agirliklari`` maddesinden okunur.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import User


def _w(ctx: Ctx) -> dict[str, float]:
    return ctx.reg.interaction_weights()


def on_registration(ctx: Ctx, user: User) -> None:
    """Birbirine yakın zamanda açılmış hesaplar."""
    w = _w(ctx)
    window = timedelta(minutes=w["yakin_kayit_dk"])
    neighbours = ctx.db.execute(
        select(User.id).where(
            User.id != user.id,
            User.email_verified.is_(True),
            User.created_at >= user.created_at - window,
            User.created_at <= user.created_at + window,
        )
    ).scalars().all()
    for other in neighbours:
        ctx.graph.add_interaction(user.id, other, w["yakin_kayit"])
        ctx.graph.add_interaction(other, user.id, w["yakin_kayit"])


def on_reply(ctx: Ctx, author_id: str, replied_to_id: str) -> None:
    if author_id != replied_to_id:
        ctx.graph.add_interaction(author_id, replied_to_id, _w(ctx)["yanit"])


def on_delegation(ctx: Ctx, user_id: str, target_id: str) -> None:
    ctx.graph.add_interaction(user_id, target_id, _w(ctx)["havale"])


def on_first_participation(ctx: Ctx, user_id: str, others_first_at: dict[str, object]) -> None:
    """Aynı başlığa kısa zaman diliminde ilk kez katılanlar.

    ``others_first_at``: başlıktaki diğer katılımcıların ilk katılım anları.
    """
    w = _w(ctx)
    window = timedelta(minutes=w["ortak_baslik_dk"])
    for other, first_at in others_first_at.items():
        if other != user_id and abs(ctx.now - first_at) <= window:
            ctx.graph.add_interaction(user_id, other, w["ortak_baslik"])
            ctx.graph.add_interaction(other, user_id, w["ortak_baslik"])
