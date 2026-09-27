"""Yönetmelik maddeleri: kurulum, okuma ve oylamayla değişim."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import RegulationChange
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.regulation import DEFAULT_ARTICLES, validate_value
from mesveret.domain.scopes import GENERAL_SCOPE_ID

ARTICLE_PREFIX = "madde:"


def article_resource_id(key: str) -> str:
    return f"{ARTICLE_PREFIX}{key}"


def install_defaults(ctx: Ctx) -> None:
    for key, article in DEFAULT_ARTICLES.items():
        ctx.graph.upsert_resource(ResourceInfo(
            article_resource_id(key), ResourceKind.YONETMELIK_MADDESI, key, GENERAL_SCOPE_ID,
        ))
        ctx.graph.set_article(key, dict(article.default))
    ctx.invalidate_regulation()


def apply_change(ctx: Ctx, key: str, value: dict[str, Any], proposal_id: int | None) -> None:
    new_value = validate_value(key, value)
    old = ctx.graph.articles().get(key)
    ctx.graph.set_article(key, new_value)
    ctx.db.add(RegulationChange(
        key=key, old_value=old, new_value=new_value, proposal_id=proposal_id, changed_at=ctx.now,
    ))
    ctx.invalidate_regulation()


def listing(ctx: Ctx) -> list[dict]:
    values = ctx.graph.articles()
    history: dict[str, list[dict]] = {}
    for ch in ctx.db.execute(select(RegulationChange).order_by(RegulationChange.id)).scalars():
        history.setdefault(ch.key, []).append({
            "old_value": ch.old_value, "new_value": ch.new_value,
            "proposal_id": ch.proposal_id, "changed_at": ch.changed_at,
        })
    return [
        {
            "key": key,
            "value": values.get(key),
            "default": article.default,
            "kind": article.kind,
            "description": article.description,
            "history": history.get(key, []),
        }
        for key, article in DEFAULT_ARTICLES.items()
    ]
