"""Yönetmelik maddeleri: kurulum, okuma, oylamayla değişim ve defterdeki izi.

Parametre maddelerinin yalnızca değeri değişir. İçerik kuralları (IK-<n>) ayrıca yönetmelik
önerisiyle eklenip kaldırılabilir; kaldırılan bir kuralın kodu bir daha kullanılmaz.

Yönetmeliğin tam hâli (değerler, değiştirilemez bayrakları, izinli aralıklar) kurulumda ve her
Karar Saati sonunda hash'iyle deftere yazılır (``YONETMELIK_DURUMU``). ``/ledger/verify`` çalışan
kodun uyguladığı yönetmeliği defterdeki son kayıtla karşılaştırır: operatörün oylamasız
değişikliği engellenmez ama tespit edilir.
"""

from __future__ import annotations

import hashlib
import json
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
    describe_range,
    range_bounds,
    range_violations,
    validate_value,
)
from mesveret.domain.scopes import GENERAL_SCOPE_ID
from mesveret.errors import DomainError
from mesveret.services import ledger

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
    record_state(ctx, None)  # başlangıç kaydı


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
            if outside := range_violations(key, new_value):
                raise DomainError(f"{key} izinli aralığın dışında: {'; '.join(outside)}.")
            ctx.graph.set_article(key, new_value)
    except RegulationError as exc:
        raise DomainError(str(exc)) from exc
    ctx.db.add(RegulationChange(
        key=key, old_value=old, new_value=new_value, proposal_id=proposal_id, changed_at=ctx.now,
    ))
    ctx.invalidate_regulation()


def _entry(ctx: Ctx, key: str, kind: str, value: Any, history: list[dict]) -> dict:
    article = DEFAULT_ARTICLES.get(key)
    return {
        "key": key,
        "value": value,
        "default": article.default if article else None,
        "kind": kind,
        "description": article.description if article else "Oylamayla eklenmiş içerik kuralı.",
        "history": history,
        "removed": value is None,
        "unchangeable": ctx.reg.is_unchangeable(key),
        "range": describe_range(key),  # değiştirilemez izinli aralık
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


# --- defterdeki iz ----------------------------------------------------------------------------------

STATE_RECORD = "YONETMELIK_DURUMU"


def state(ctx: Ctx) -> dict[str, dict]:
    """Çalışan kodun uyguladığı yönetmeliğin tam hâli: değer, değiştirilemezlik, izinli aralık
    (metni ve uygulanan sınırları)."""
    values = ctx.graph.articles()
    unchangeable = ctx.graph.unchangeable_articles()
    return {
        key: {"deger": values.get(key), "degistirilemez": key in unchangeable,
              "izinli_aralik": describe_range(key), "izinli_sinirlar": range_bounds(key)}
        for key in sorted(set(values) | set(DEFAULT_ARTICLES))
    }


def state_hash(st: dict) -> str:
    canonical = json.dumps(st, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_state(ctx: Ctx, session_id: int | None) -> None:
    st = state(ctx)
    ledger.enqueue(ctx, STATE_RECORD, {"oturum": session_id, "hash": state_hash(st), "durum": st})


def verify_state(ctx: Ctx) -> dict:
    """Çalışan kodun yönetmeliğini defterdeki son ``YONETMELIK_DURUMU`` kaydıyla karşılaştırır."""
    current = state(ctx)
    current_hash = state_hash(current)
    rec = ledger.last_of_type(ctx.ledger, STATE_RECORD)
    if rec is None:
        return {"status": "kayit_yok", "current_hash": current_hash, "recorded_hash": None,
                "differences": [], "message": "Defterde yönetmelik kaydı yok."}
    payload = rec["payload"]
    recorded = payload.get("durum", {})
    differences = sorted(k for k in set(current) | set(recorded)
                         if current.get(k) != recorded.get(k))
    same = payload.get("hash") == current_hash
    where = f"#{payload['oturum']} numaralı oturumun sonunda" if payload.get("oturum") else "kurulumda"
    return {
        "status": "tutarli" if same else "farkli",
        "current_hash": current_hash,
        "recorded_hash": payload.get("hash"),
        "record_hash": rec.get("hash"),
        "record_seq": rec.get("seq"),
        "session": payload.get("oturum"),
        "recorded_at": rec.get("ts"),
        "record_consistent": state_hash(recorded) == payload.get("hash"),
        "differences": differences,
        "message": (f"Çalışan kodun yönetmeliği {where} deftere yazılan hâliyle aynı." if same else
                    f"Çalışan kodun yönetmeliği {where} deftere yazılan hâlinden farklı: "
                    f"{', '.join(differences)}. Bu değişiklik oylamasız yapılmış olabilir."),
    }
