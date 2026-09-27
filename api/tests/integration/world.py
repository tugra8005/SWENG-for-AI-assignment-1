"""Entegrasyon testleri için küçük bir dünya: alanlar, kapsamlar, kaynaklar, yönetmelik, Hâtif.

Alan ağacı:
    kultur ─┬─ sinema ── belgesel
            └─ edebiyat
    kent ──── ulasim
"""

from __future__ import annotations

from datetime import date, timedelta

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.scopes import ScopeSubtype
from mesveret.services import auth, ontology, oracle, scheduler

AREAS = [
    ("kultur", "Kültür", None, ("kültür", "sanat")),
    ("sinema", "Sinema", "kultur", ("sinema", "film", "yönetmen")),
    ("belgesel", "Belgesel", "sinema", ("belgesel",)),
    ("edebiyat", "Edebiyat", "kultur", ("edebiyat", "roman", "şiir")),
    ("kent", "Kent", None, ("kent", "şehir", "mahalle")),
    ("ulasim", "Ulaşım", "kent", ("ulaşım", "otobüs", "bisiklet", "metro")),
]

RESOURCES = [
    ResourceInfo(
        "butce", ResourceKind.ORTAK, "Etkinlik bütçesi", "genel",
        divisible=True, division_type=ScopeSubtype.SEHIR,
        shares={"sehir:istanbul": 4000, "sehir:ankara": 3000, "sehir:izmir": 2000},
        aliases=("bütçe", "etkinlik bütçe"),
    ),
    ResourceInfo("salon", ResourceKind.ORTAK, "Ortak toplantı salonu", "genel",
                 aliases=("salon", "toplantı salon")),
]


def build_world(ctx: Ctx) -> None:
    ontology.install_base(ctx, AREAS, RESOURCES, cities=["İstanbul", "Ankara", "İzmir"])
    oracle.ensure_oracle(ctx)
    scheduler.ensure_state(ctx)
    ctx.db.commit()


def make_user(
    ctx: Ctx,
    nickname: str,
    *,
    city: str = "İstanbul",
    birth: date = date(1995, 5, 5),
    created_days_ago: int = 400,
    interests: tuple[str, ...] = (),
) -> User:
    """Doğrulanmış, geçmiş tarihli bir kullanıcı oluşturur (bekleme süreleri dolmuş)."""
    at = ctx.now - timedelta(days=created_days_ago)
    user = auth.create_verified_user(
        ctx.at(at), nickname=nickname, full_name=f"{nickname.title()} Test",
        email=f"{nickname}@example.com", password="parola-123", birth_date=birth,
        city=city, district="Merkez",
    )
    for area in interests:
        ontology.join_interest(ctx.at(at), user, area)
    ctx.db.commit()
    return user
