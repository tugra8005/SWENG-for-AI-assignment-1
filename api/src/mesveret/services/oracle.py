"""Hâtif servis hesabı: kural tabanlı sembolik bilirkişi (gerçek bir yapay zekâ çağrısı yok)."""

from __future__ import annotations

from datetime import timedelta

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.domain.scopes import GENERAL_SCOPE_ID, Membership, MembershipReason, interest_scope_id

ORACLE_ID = "hatif"
ORACLE_NICKNAME = "Hâtif"


def ensure_oracle(ctx: Ctx) -> User:
    """Hâtif hesabını ve üyeliklerini kurar: GENEL ve tüm ILGI kapsamları (NITELIK değil)."""
    user = ctx.db.get(User, ORACLE_ID)
    since = ctx.now - timedelta(days=3650)
    if user is None:
        user = User(
            id=ORACLE_ID, nickname=ORACLE_NICKNAME, nickname_key="hâtif",
            full_name="Hâtif (servis hesabı)", email=None, password_hash=None,
            role="ORACLE", email_verified=True, created_at=since,
        )
        ctx.db.add(user)
        ctx.db.flush()
    g = ctx.graph
    g.upsert_user(user.id, user.nickname, user.role, user.created_at)
    g.set_membership(user.id, Membership(GENERAL_SCOPE_ID, user.created_at, MembershipReason.KAYIT))
    for area in g.all_areas():
        g.set_membership(
            user.id, Membership(interest_scope_id(area.id), user.created_at, MembershipReason.KATILIM)
        )
    return user
