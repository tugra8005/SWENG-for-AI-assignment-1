"""Profil: takma ada tıklayınca görünen herkese açık kayıt ve yalnızca sahibine görünen alanlar."""

from __future__ import annotations

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.data.iller import ILLER
from mesveret.db.models import User
from mesveret.domain.counselor import counselor_areas
from mesveret.errors import DomainError, NotFound
from mesveret.services import ontology
from mesveret.services.auth import nickname_key

ROLE_LABELS = {"CITIZEN": "Yurttaş", "ORACLE": "Hâtif"}


def find_user(ctx: Ctx, nickname: str) -> User:
    user = ctx.db.execute(
        select(User).where(User.nickname_key == nickname_key(nickname), User.email_verified.is_(True))
    ).scalar_one_or_none()
    if user is None:
        raise NotFound("Bu takma adla bir yurttaş bulunamadı.")
    return user


def users_by_id(ctx: Ctx, ids) -> dict[str, User]:
    ids = list(set(ids))
    if not ids:
        return {}
    return {u.id: u for u in ctx.db.execute(select(User).where(User.id.in_(ids))).scalars()}


def nickname_map(ctx: Ctx, ids) -> dict[str, str]:
    return {uid: u.nickname for uid, u in users_by_id(ctx, ids).items()}


def public_profile(ctx: Ctx, user: User, viewer: User | None = None) -> dict:
    # Müşavir etiketi yürürlükteki havalelerden hesaplanır; süresi dolanlar düştükçe kaybolabilir.
    incoming = ctx.graph.incoming_delegations(user.id, active_at=ctx.now)
    counselor = counselor_areas(incoming, ctx.reg)
    roles = [ROLE_LABELS.get(user.role, user.role)]
    if counselor:
        roles.append("Müşavir")
    received = sorted(
        ({"area_id": a, "name": ontology.area_name(ctx, a), "count": n} for a, n in incoming.items()),
        key=lambda x: (x["area_id"] is not None, x["name"]),
    )
    return {
        "id": user.id,
        "nickname": user.nickname,
        "roles": roles,
        "counselor_areas": [
            {"area_id": a, "name": ontology.area_name(ctx, a), "count": incoming[a]} for a in counselor
        ],
        "delegations_received": received,
        "member_since": user.created_at,
        "is_self": viewer is not None and viewer.id == user.id,
    }


def private_profile(ctx: Ctx, user: User) -> dict:
    ontology.sync_age_membership(ctx, user)
    body = public_profile(ctx, user, viewer=user)
    body.update({
        "full_name": user.full_name,
        "email": user.email,
        "birth_date": user.birth_date,
        "address": {"city": user.city, "district": user.district, "address_line": user.address_line},
        "memberships": [ontology.membership_view(ctx, m) for m in ctx.graph.memberships(user.id)],
    })
    # Verilen ve alınan havaleler kalan süreleriyle (Havale sayfasıyla aynı görünüm).
    from mesveret.services import delegation

    mine = delegation.my_delegations(ctx, user)
    body.update({
        "delegations_given": mine["given"],
        "delegations_received_list": mine["received_list"],
        "expiring_given": mine["expiring_given"],
        "expiring_received": mine["expiring_received"],
        "warning_days": mine["warning_days"],
    })
    return body


def nickname_of(ctx: Ctx, user_id: str) -> str:
    u = ctx.db.get(User, user_id)
    return u.nickname if u else user_id


def change_address(ctx: Ctx, user: User, city: str, district: str, address_line: str) -> None:
    if city not in ILLER:
        raise DomainError("İl, Türkiye'nin 81 ilinden biri olmalı.")
    if not 2 <= len(district.strip()) <= 60:
        raise DomainError("İlçe 2–60 karakter olmalı.")
    if city != user.city:
        ontology.change_city(ctx, user, city)
    user.city = city
    user.district = district.strip()
    user.address_line = address_line.strip() or None
    ctx.commit()
