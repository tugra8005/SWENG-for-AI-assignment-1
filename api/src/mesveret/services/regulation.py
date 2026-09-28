"""Yönetmelik maddeleri: kurulum, okuma ve oylamayla değişim.

Parametre maddelerinin yalnızca değeri değişir. İçerik kuralları (IK-<n>) ayrıca yönetmelik
önerisiyle eklenip kaldırılabilir; kaldırılan bir kuralın kodu bir daha kullanılmaz.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import Proposal, RegulationChange
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.regulation import (
    CONTENT_RULE_KIND,
    DEFAULT_ARTICLES,
    RegulationError,
    article_kind,
    content_rule_number,
    validate_value,
)
from mesveret.domain.scopes import GENERAL_SCOPE_ID
from mesveret.errors import DomainError

ARTICLE_PREFIX = "madde:"
# Kural ekleme önerisinin ETKILER etiketi: henüz var olmayan kuralın yerine kural kümesi.
CONTENT_RULES_RESOURCE_ID = f"{ARTICLE_PREFIX}icerik_kurallari"
ACTIONS = ("degistir", "ekle", "kaldir")


def article_resource_id(key: str) -> str:
    return f"{ARTICLE_PREFIX}{key}"


def _article_resource(ctx: Ctx, key: str) -> None:
    ctx.graph.upsert_resource(ResourceInfo(
        article_resource_id(key), ResourceKind.YONETMELIK_MADDESI, key, GENERAL_SCOPE_ID,
    ))


def install_defaults(ctx: Ctx) -> None:
    for key, article in DEFAULT_ARTICLES.items():
        _article_resource(ctx, key)
        ctx.graph.set_article(key, dict(article.default))
        if article.unchangeable:
            ctx.graph.set_unchangeable(key)
    ctx.graph.upsert_resource(ResourceInfo(
        CONTENT_RULES_RESOURCE_ID, ResourceKind.YONETMELIK_MADDESI, "İçerik kuralları",
        GENERAL_SCOPE_ID,
    ))
    ctx.invalidate_regulation()


def next_content_rule_code(ctx: Ctx) -> str:
    """Hiç kullanılmamış ilk kod: yürürlükteki, kaldırılmış ve önerilmiş kodların üstü."""
    used = set(ctx.graph.articles())
    used |= set(ctx.db.execute(select(RegulationChange.key)).scalars())
    used |= {p.payload.get("article_key", "") for p in ctx.db.execute(
        select(Proposal).where(Proposal.type == "YONETMELIK")).scalars()}
    top = max((content_rule_number(k) or 0 for k in used), default=0)
    return f"IK-{top + 1}"


def apply_change(ctx: Ctx, key: str, value: dict[str, Any] | None, proposal_id: int | None,
                 action: str = "degistir") -> None:
    old = ctx.graph.articles().get(key)
    if key in ctx.graph.unchangeable_articles():
        # R8 öneriyi açılışta reddeder; bu ikinci savunma hattıdır.
        raise DomainError(f"Bu madde değiştirilemez: {key}.")
    try:
        if action == "kaldir":
            if old is None or article_kind(key) != CONTENT_RULE_KIND:
                raise DomainError(f"{key} yürürlükte bir içerik kuralı değil; kaldırılamaz.")
            ctx.graph.delete_article(key)
            new_value = None
        elif action == "ekle":
            if old is not None or article_kind(key) != CONTENT_RULE_KIND:
                raise DomainError(f"{key} kodu kullanılamaz.")
            new_value = validate_value(key, value)
            _article_resource(ctx, key)
            ctx.graph.set_article(key, new_value)
        else:
            if old is None:
                raise DomainError(f"{key} yürürlükte değil; değiştirilemez.")
            new_value = validate_value(key, value)
            ctx.graph.set_article(key, new_value)
    except RegulationError as exc:
        raise DomainError(str(exc)) from exc
    ctx.db.add(RegulationChange(
        key=key, old_value=old, new_value=new_value, proposal_id=proposal_id, changed_at=ctx.now,
    ))
    ctx.invalidate_regulation()


def _entry(ctx: Ctx, key: str, kind: str, value: Any, history: list[dict]) -> dict:
    article = DEFAULT_ARTICLES.get(key)
    floor = ctx.reg.floor_for(key)
    return {
        "key": key,
        "value": value,
        "default": article.default if article else None,
        "kind": kind,
        "description": article.description if article else "Oylamayla eklenmiş içerik kuralı.",
        "history": history,
        "removed": value is None,
        "unchangeable": ctx.reg.is_unchangeable(key),
        "floor": None if floor is None else {
            "key": floor[0], "oran": f"{floor[1].value.numerator}/{floor[1].value.denominator}",
            "karsilastirma": floor[1].comparison},
    }


def listing(ctx: Ctx) -> list[dict]:
    values = ctx.graph.articles()
    history: dict[str, list[dict]] = {}
    for ch in ctx.db.execute(select(RegulationChange).order_by(RegulationChange.id)).scalars():
        history.setdefault(ch.key, []).append({
            "old_value": ch.old_value, "new_value": ch.new_value,
            "proposal_id": ch.proposal_id, "changed_at": ch.changed_at,
        })
    params = [_entry(ctx, key, a.kind, values.get(key), history.get(key, []))
              for key, a in DEFAULT_ARTICLES.items() if a.kind != CONTENT_RULE_KIND]
    # Yürürlükteki ve kaldırılmış içerik kuralları, numara sırasıyla.
    rule_keys = sorted({k for k in [*values, *history] if content_rule_number(k)},
                       key=lambda k: content_rule_number(k) or 0)
    rules = [_entry(ctx, k, CONTENT_RULE_KIND, values.get(k), history.get(k, []))
             for k in rule_keys]
    return params + rules
