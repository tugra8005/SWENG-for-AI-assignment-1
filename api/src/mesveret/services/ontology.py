"""Ontoloji kurulumu, kapsam üyelikleri ve oy hakkı (R5)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select

from mesveret.clock import ISTANBUL
from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.domain.ontology import AreaInfo, ResourceInfo, ResourceKind, ScopeInfo
from mesveret.domain.rules import VoteRight, format_date
from mesveret.domain.scopes import (
    AGE_GROUPS,
    GENERAL_SCOPE_ID,
    Membership,
    MembershipReason,
    ScopeSubtype,
    ScopeType,
    age_group,
    age_group_since,
    age_scope_id,
    city_scope_id,
    has_vote_right,
    interest_scope_id,
    vote_right_starts,
)
from mesveret.domain.text import turkish_lower
from mesveret.errors import Conflict, NotFound
from mesveret.services import regulation

_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def slugify(name: str) -> str:
    folded = turkish_lower(name).translate(_FOLD)
    return "-".join("".join(c if c.isalnum() else " " for c in folded).split())


# --- kurulum --------------------------------------------------------------------------------------


def install_base(
    ctx: Ctx,
    areas: Sequence[tuple[str, str, str | None, tuple[str, ...]]],
    resources: Iterable[ResourceInfo],
    cities: Iterable[str] = (),
) -> None:
    """Genel ve yaş kapsamlarını, alanları (ILGI kapsamlarıyla), kaynakları ve yönetmeliği kurar."""
    g = ctx.graph
    g.upsert_scope(ScopeInfo(GENERAL_SCOPE_ID, ScopeType.GENEL, "Genel"), set())
    for name, _, _ in AGE_GROUPS:
        g.upsert_scope(
            ScopeInfo(age_scope_id(name), ScopeType.NITELIK, f"{name} yaş", ScopeSubtype.YAS_GRUBU, name),
            {GENERAL_SCOPE_ID},
        )
    for city in cities:
        ensure_city_scope(ctx, city)
    for area_id, name, parent, keywords in areas:
        g.upsert_area(AreaInfo(area_id, name, parent, tuple(keywords)))
        g.upsert_scope(
            ScopeInfo(interest_scope_id(area_id), ScopeType.ILGI, f"{name} ilgi kapsamı", None, area_id),
            {GENERAL_SCOPE_ID},
        )
        g.upsert_resource(ResourceInfo(f"alan:{area_id}", ResourceKind.ALAN, name, GENERAL_SCOPE_ID))
    for r in resources:
        g.upsert_resource(r)
    regulation.install_defaults(ctx)


def ensure_city_scope(ctx: Ctx, city: str) -> str:
    scope_id = city_scope_id(slugify(city))
    if ctx.graph.scope(scope_id) is None:
        ctx.graph.upsert_scope(
            ScopeInfo(scope_id, ScopeType.NITELIK, city, ScopeSubtype.SEHIR, city), {GENERAL_SCOPE_ID}
        )
    return scope_id


# --- üyelik -------------------------------------------------------------------------------------


def _start_of_day(d) -> datetime:
    return datetime.combine(d, time.min, tzinfo=ISTANBUL).astimezone(UTC)


def sync_age_membership(ctx: Ctx, user: User) -> None:
    """Yaş grubu üyeliğini doğum tarihine göre günceller (sistem hesaplar)."""
    if user.birth_date is None:
        return
    today = ctx.now.astimezone(ISTANBUL).date()
    group = age_group(user.birth_date, today)
    current = {m.scope_id: m for m in ctx.graph.memberships(user.id)
               if m.scope_id.startswith("yas:")}
    target = age_scope_id(group) if group else None
    for scope_id in current:
        if scope_id != target:
            ctx.graph.remove_membership(user.id, scope_id)
    if group is not None and target is not None and target not in current:
        since = max(_start_of_day(age_group_since(user.birth_date, group)), user.created_at)
        ctx.graph.set_membership(user.id, Membership(target, since, MembershipReason.YAS))


def register_memberships(ctx: Ctx, user: User) -> None:
    g = ctx.graph
    g.upsert_user(user.id, user.nickname, user.role, user.created_at)
    g.set_membership(user.id, Membership(GENERAL_SCOPE_ID, user.created_at, MembershipReason.KAYIT))
    if user.city:
        scope_id = ensure_city_scope(ctx, user.city)
        user.city_scope_id = scope_id
        g.set_membership(user.id, Membership(scope_id, user.created_at, MembershipReason.KAYIT))
    sync_age_membership(ctx, user)


def change_city(ctx: Ctx, user: User, new_city: str) -> None:
    old = user.city_scope_id
    new = ensure_city_scope(ctx, new_city)
    if old == new:
        return
    if old:
        ctx.graph.remove_membership(user.id, old)
    ctx.graph.set_membership(user.id, Membership(new, ctx.now, MembershipReason.ADRES_DEGISIKLIGI))
    user.city_scope_id = new
    user.address_changed_at = ctx.now


def join_interest(ctx: Ctx, user: User, area_id: str) -> Membership:
    if ctx.graph.area(area_id) is None:
        raise NotFound("Alan bulunamadı.")
    scope_id = interest_scope_id(area_id)
    if any(m.scope_id == scope_id for m in ctx.graph.memberships(user.id)):
        raise Conflict("Bu alanın ilgi kapsamına zaten üyesiniz.")
    m = Membership(scope_id, ctx.now, MembershipReason.KATILIM)
    ctx.graph.set_membership(user.id, m)
    return m


def leave_interest(ctx: Ctx, user: User, area_id: str) -> None:
    scope_id = interest_scope_id(area_id)
    if not any(m.scope_id == scope_id for m in ctx.graph.memberships(user.id)):
        raise NotFound("Bu alanın ilgi kapsamına üye değilsiniz.")
    ctx.graph.remove_membership(user.id, scope_id)


# --- oy hakkı -----------------------------------------------------------------------------------


def vote_right(ctx: Ctx, user_id: str, scope_id: str) -> VoteRight:
    m = ctx.graph.scope_members(scope_id).get(user_id)
    if m is None:
        scope = ctx.graph.scope(scope_id)
        name = scope.name if scope else scope_id
        return VoteRight(False, f"{name} kapsamının üyesi değilsiniz.")
    if not has_vote_right(m, ctx.now, ctx.reg):
        starts = vote_right_starts(m, ctx.reg)
        return VoteRight(False, f"Bu kapsamda oy hakkınız {format_date(starts)} tarihinde doğacak.")
    return VoteRight(True)


def eligible_voters(ctx: Ctx, scope_id: str) -> dict[str, Membership]:
    """Kapsamda şu an oy hakkı olan üyeler (R5)."""
    return {
        uid: m for uid, m in ctx.graph.scope_members(scope_id).items()
        if has_vote_right(m, ctx.now, ctx.reg)
    }


def active_member_count(ctx: Ctx, scope_id: str) -> int:
    """Kapsamda son ``aktiflik_gun`` günde giriş yapmış üye sayısı (itiraz eşiği için)."""
    members = list(ctx.graph.scope_members(scope_id))
    if not members:
        return 0
    since = ctx.now - ctx.reg.objection_activity_window()
    rows = ctx.db.execute(
        select(User.id).where(User.id.in_(members), User.last_login_at >= since)
    ).scalars().all()
    return len(rows)


def membership_view(ctx: Ctx, m: Membership) -> dict:
    scope = ctx.graph.scope(m.scope_id)
    starts = vote_right_starts(m, ctx.reg)
    return {
        "scope_id": m.scope_id,
        "name": scope.name if scope else m.scope_id,
        "type": str(scope.type) if scope else None,
        "since": m.since,
        "reason": str(m.reason),
        "vote_right_from": starts if starts > m.since else None,
        "has_vote_right": ctx.now >= starts,
    }


def scope_label(ctx: Ctx, scope_id: str) -> str:
    scope = ctx.graph.scope(scope_id)
    return scope.name if scope else scope_id


def area_name(ctx: Ctx, area_id: str | None) -> str:
    if area_id is None:
        return "Genel"
    area = ctx.graph.area(area_id)
    return area.name if area else area_id


def far_past(ctx: Ctx) -> datetime:
    return ctx.now - timedelta(days=3650)
