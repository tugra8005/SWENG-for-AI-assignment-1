"""Yönetmelik maddeleri: kurulum, okuma, oylamayla değişim ve defterdeki izi.

Parametre maddelerinin yalnızca değeri değişir. İçerik kuralları (IK-<n>) ayrıca yönetmelik
önerisiyle eklenip kaldırılabilir; kaldırılan bir kuralın kodu bir daha kullanılmaz.

Yönetmeliğin tam hâli (değerler, değiştirilemez bayrakları, izinli aralıklar) kurulumda ve her
Karar Saati sonunda hash'iyle deftere yazılır (``YONETMELIK_DURUMU``). ``/ledger/verify`` çalışan
kodun uyguladığı yönetmeliği defterdeki son kayıtla karşılaştırır: operatörün oylamasız
değişikliği engellenmez ama tespit edilir. Karar Saati kapanışında oylamasız farklar deftere
yazılır ve maddeler son oylanmış hâline döndürülür; oylamasız bir değer bir oturumdan fazla yaşamaz.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import LedgerOutbox, Proposal, RegulationChange
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


def _differences(current: dict, recorded: dict) -> list[str]:
    return sorted(k for k in set(current) | set(recorded) if current.get(k) != recorded.get(k))


def verify_state(ctx: Ctx) -> dict:
    """Çalışan kodun yönetmeliğini defterdeki son ``YONETMELIK_DURUMU`` kaydıyla karşılaştırır ve
    defterin tamamındaki ``OYLAMASIZ_DEGISIKLIK`` kayıtlarını geçmiş olarak ekler."""
    current = state(ctx)
    current_hash = state_hash(current)
    past = silent_change_history(ctx)
    rec = ledger.last_of_type(ctx.ledger, STATE_RECORD)
    if rec is None:
        return {"status": "kayit_yok", "current_hash": current_hash, "recorded_hash": None,
                "differences": [], "history": past, "message": "Defterde yönetmelik kaydı yok."}
    payload = rec["payload"]
    recorded = payload.get("durum", {})
    differences = _differences(current, recorded)
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
        "history": past,
        "message": (f"Çalışan kodun yönetmeliği {where} deftere yazılan hâliyle aynı." if same else
                    f"Çalışan kodun yönetmeliği {where} deftere yazılan hâlinden farklı: "
                    f"{', '.join(differences)}. Bu değişiklik oylamasız yapılmış olabilir; bir "
                    "sonraki Karar Saati kapanışında geri alınır."),
    }


# --- oylamasız değişikliğin kapanışta tespiti ve geri alınması -----------------------------------

SILENT_CHANGE = "OYLAMASIZ_DEGISIKLIK"
SILENT_REVERT = "OYLAMASIZ_DEGISIKLIK_GERI_ALINDI"
CODE_LEVEL = ("izinli_aralik", "izinli_sinirlar")


def reference_state(ctx: Ctx) -> dict | None:
    """Son oylanmış hâl: en son ``YONETMELIK_DURUMU`` kaydı.

    Kaynak outbox'taki son satırdır, çünkü defterde henüz olmayan (bekleyen) bir kayıt defterdeki
    son kayıttan yenidir; eski kayıtla karşılaştırmak oylanmış bir değişikliği oylamasız sayardı.
    Satır deftere ulaştıysa defterdeki kopyası esas alınır; defter otoritedir.
    """
    row = ctx.db.execute(
        select(LedgerOutbox).where(LedgerOutbox.type == STATE_RECORD)
        .order_by(LedgerOutbox.id.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.ledger_seq is not None:
        rec = ledger.record_at(ctx.ledger, row.ledger_seq)
        if rec is not None and rec.get("type") == STATE_RECORD:
            return {**rec["payload"], "kayit_seq": rec["seq"], "kayit_hash": rec["hash"]}
    return {**row.payload, "kayit_seq": row.ledger_seq, "kayit_hash": row.ledger_hash}


def _restore(ctx: Ctx, key: str, was: dict | None, found: dict | None) -> tuple[list, list]:
    """Maddeyi kayıttaki hâline döndürür. Değer ve bayrak veridir, geri alınır; izinli aralık ve
    kodla gelen yeni madde çalışan koddandır, veriden geri alınamaz."""
    restored: list[str] = []
    not_restored: list[str] = []
    found = found or {}
    if was is None and key in DEFAULT_ARTICLES:
        return restored, ["madde"]  # kayıttan sonra kodla eklenmiş madde
    was = was or {"deger": None, "degistirilemez": False}
    if found.get("deger") != was.get("deger"):
        if was.get("deger") is None:
            ctx.graph.delete_article(key)
        else:
            _article_resource(ctx, key)
            ctx.graph.set_article(key, was["deger"])
        restored.append("deger")
    if bool(found.get("degistirilemez")) != bool(was.get("degistirilemez")):
        if was.get("degistirilemez"):
            ctx.graph.set_unchangeable(key)
        else:
            ctx.graph.clear_unchangeable(key)
        restored.append("degistirilemez")
    if any(found.get(f) != was.get(f) for f in CODE_LEVEL):
        not_restored.append("izinli_aralik")
    return restored, not_restored


def restore_voted_state(ctx: Ctx, session_id: int) -> list[str]:
    """Karar Saati kapanışında, oturumun değişikliklerinden önce: yönetmeliği son kayıtla
    karşılaştırır; her fark için ``OYLAMASIZ_DEGISIKLIK`` yazar, maddeyi son oylanmış hâline
    döndürür ve geri almayı ``OYLAMASIZ_DEGISIKLIK_GERI_ALINDI`` olarak yazar. Farklı maddeleri döner.
    """
    ref = reference_state(ctx)
    if ref is None:
        return []
    recorded = ref.get("durum", {})
    current = state(ctx)
    differences = _differences(current, recorded)
    for key in differences:
        was, found = recorded.get(key), current.get(key)
        ledger.enqueue(ctx, SILENT_CHANGE, {
            "madde": key, "kayittaki": was, "bulunan": found, "tespit_zamani": ctx.now.isoformat(),
            "oturum": session_id, "karsilastirilan_kayit": ref.get("kayit_seq"),
        })
        restored, not_restored = _restore(ctx, key, was, found)
        ledger.enqueue(ctx, SILENT_REVERT, {
            "madde": key, "oturum": session_id, "geri_alinan": restored,
            "geri_alinamayan": not_restored, "simdiki": state(ctx).get(key),
            "not": ("Kod düzeyindeki fark (izinli aralık ya da kodla eklenen madde) veriden geri "
                    "alınamaz." if not_restored else "Madde son oylanmış hâline döndü."),
        })
    if differences:
        ctx.invalidate_regulation()
    return differences


def silent_change_history(ctx: Ctx) -> list[dict] | None:
    """Defterin tamamındaki oylamasız değişiklikler, en yenisi önce. Deftere ulaşılamazsa ``None``."""
    found = ledger.records_of_type(ctx.ledger, SILENT_CHANGE)
    reverts = ledger.records_of_type(ctx.ledger, SILENT_REVERT)
    if found is None:
        return None
    by_key = {(r["payload"].get("oturum"), r["payload"].get("madde")): r for r in reverts or []}
    out = []
    for rec in reversed(found):
        p = rec["payload"]
        was, now = p.get("kayittaki") or {}, p.get("bulunan") or {}
        revert = by_key.get((p.get("oturum"), p.get("madde")))
        rp = revert["payload"] if revert else {}
        out.append({
            "madde": p.get("madde"),
            "tur": article_kind(p["madde"]) if p.get("madde") else None,
            "kayittaki": was.get("deger"),
            "bulunan": now.get("deger"),
            "alanlar": [f for f in ("deger", "degistirilemez", "izinli_aralik")
                        if was.get(f) != now.get(f)],
            "kayittaki_aralik": was.get("izinli_aralik"),
            "bulunan_aralik": now.get("izinli_aralik"),
            "tespit_zamani": p.get("tespit_zamani"),
            "oturum": p.get("oturum"),
            "hash": rec.get("hash"),
            "seq": rec.get("seq"),
            "geri_alinan": rp.get("geri_alinan"),
            "geri_alinamayan": rp.get("geri_alinamayan"),
            "geri_alma_hash": revert.get("hash") if revert else None,
        })
    return out
