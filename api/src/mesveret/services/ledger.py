"""Defter bağlantısı: outbox, gönderim, hash'in içeriğe geri yazılması ve düğüm doğrulaması.

Deftere gidecek her kayıt, onu doğuran değişiklikle aynı PostgreSQL işleminde
``ledger_outbox`` tablosuna yazılır. ``flush`` bekleyen kayıtları sırayla lidere gönderir;
lider erişilemezse kayıtlar bekler ve zamanlayıcı yeniden dener. Böylece defterdeki sıra
PostgreSQL'deki sırayla aynı kalır.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from sqlalchemy import select, text

from mesveret.db.base import Base
from mesveret.db.models import LedgerOutbox

if TYPE_CHECKING:
    from mesveret.context import Ctx

log = logging.getLogger("mesveret.ledger")

FLUSH_LOCK_KEY = 424242


# --- istemciler ---------------------------------------------------------------------------------


class LedgerClient(Protocol):
    def append(self, type_: str, payload: Any, ts: str) -> dict: ...
    def node_urls(self) -> list[str]: ...
    def get(self, url: str, path: str) -> Any: ...
    def reset(self) -> None: ...


class HttpLedgerClient:
    def __init__(self, leader_url: str, node_urls: list[str], token: str, timeout: float = 5.0):
        self.leader_url = leader_url
        self._nodes = node_urls
        self._headers = {"X-Ledger-Token": token}
        self._timeout = timeout

    def append(self, type_: str, payload: Any, ts: str) -> dict:
        r = httpx.post(
            f"{self.leader_url}/append", json={"type": type_, "payload": payload, "ts": ts},
            headers=self._headers, timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json()

    def node_urls(self) -> list[str]:
        return list(self._nodes)

    def get(self, url: str, path: str) -> Any:
        r = httpx.get(f"{url}{path}", timeout=self._timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def reset(self) -> None:
        httpx.post(
            f"{self.leader_url}/_dev/reset", headers=self._headers, timeout=self._timeout
        ).raise_for_status()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class FakeLedgerClient:
    """Testler için bellek içi tek düğümlü defter (aynı hash formülü)."""

    URL = "memory://ledger"

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.fail = False
        self.lock = threading.Lock()

    def append(self, type_: str, payload: Any, ts: str) -> dict:
        if self.fail:
            raise ConnectionError("sahte defter kapalı")
        with self.lock:
            prev = self.records[-1]["hash"] if self.records else "0" * 64
            ts_n = datetime.fromisoformat(ts).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            ph = hashlib.sha256(_canonical(payload)).hexdigest()
            h = hashlib.sha256((prev + ph + ts_n + type_).encode()).hexdigest()
            rec = {"seq": len(self.records) + 1, "prev_hash": prev, "ts": ts_n, "type": type_,
                   "payload": json.loads(_canonical(payload)), "payload_hash": ph, "hash": h}
            self.records.append(rec)
            return rec

    def node_urls(self) -> list[str]:
        return [self.URL]

    def get(self, url: str, path: str) -> Any:
        if path == "/verify":
            return {"ok": True, "length": len(self.records), "reason": None}
        if path.startswith("/records/by-hash/"):
            prefix = path.rsplit("/", 1)[1]
            return next((r for r in self.records if r["hash"].startswith(prefix)), None)
        if path.startswith("/records/"):
            seq = int(path.rsplit("/", 1)[1])
            return self.records[seq - 1] if 0 < seq <= len(self.records) else None
        raise ValueError(path)

    def reset(self) -> None:
        self.records.clear()

    def of_type(self, type_: str) -> list[dict]:
        return [r for r in self.records if r["type"] == type_]


# --- outbox -------------------------------------------------------------------------------------


def _model_by_table() -> dict[str, type]:
    return {m.class_.__tablename__: m.class_ for m in Base.registry.mappers}


def enqueue(
    ctx: Ctx, type_: str, payload: Any, *, ref: Any = None, ref_attr: str = "ledger_hash"
) -> LedgerOutbox:
    """Deftere gidecek kaydı outbox'a ekler. ``ref`` verilirse hash o satıra geri yazılır."""
    row = LedgerOutbox(type=type_, payload=payload, ts=ctx.now)
    if ref is not None:
        ctx.db.flush()
        row.ref_table = ref.__tablename__
        row.ref_id = str(ref.id)
        row.ref_attr = ref_attr
    ctx.db.add(row)
    return row


def flush(ctx: Ctx, limit: int = 500) -> int:
    """Bekleyen kayıtları sırayla gönderir; gönderilen sayısını döner."""
    db = ctx.db
    got_lock = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": FLUSH_LOCK_KEY}
    ).scalar()
    if not got_lock:
        db.rollback()
        return 0
    models = _model_by_table()
    last_ts = db.execute(
        select(LedgerOutbox.ts).where(LedgerOutbox.sent_at.is_not(None))
        .order_by(LedgerOutbox.id.desc()).limit(1)
    ).scalar()
    pending = db.execute(
        select(LedgerOutbox).where(LedgerOutbox.sent_at.is_(None))
        .order_by(LedgerOutbox.id).limit(limit)
    ).scalars().all()
    sent = 0
    for row in pending:
        ts = row.ts if last_ts is None or row.ts >= last_ts else last_ts
        try:
            rec = ctx.ledger.append(row.type, row.payload, ts.isoformat())
        except Exception as exc:  # noqa: BLE001  (lider erişilemez: kayıt bekler)
            log.warning("defter gönderimi başarısız (outbox #%s): %s", row.id, exc)
            break
        row.ts = ts
        row.sent_at = datetime.now(UTC)
        row.ledger_seq = rec["seq"]
        row.ledger_hash = rec["hash"]
        if row.ref_table and (model := models.get(row.ref_table)):
            key = int(row.ref_id) if row.ref_id and row.ref_id.isdigit() else row.ref_id
            target = db.get(model, key)
            if target is not None:
                setattr(target, row.ref_attr or "ledger_hash", rec["hash"])
        last_ts = ts
        sent += 1
    db.commit()
    return sent


# --- düğüm doğrulaması ------------------------------------------------------------------------------


@dataclass
class NodeReport:
    reachable: bool
    ok: bool
    length: int
    reason: str | None
    hash_at: dict[int, str] = field(default_factory=dict)


def compare_nodes(urls: list[str], reports: dict[str, NodeReport]) -> dict:
    """Düğümleri referans düğüme (lider, bozuksa en uzun sağlam düğüm) göre karşılaştırır.

    Durumlar: ``tutarli``, ``geride``, ``tutarsiz``, ``butunluk_bozuk``, ``erisilemiyor``.
    Hash zinciri öneki kapsadığı için ortak uzunluktaki tek hash karşılaştırması yeterlidir.
    """
    healthy = [u for u in urls if reports[u].reachable and reports[u].ok]
    ref = None
    if healthy:
        ref = urls[0] if urls[0] in healthy else max(healthy, key=lambda u: reports[u].length)
    nodes = []
    for url in urls:
        r = reports[url]
        entry: dict[str, Any] = {"url": url, "length": r.length}
        if not r.reachable:
            entry.update(status="erisilemiyor", message=f"Düğüme ulaşılamıyor: {r.reason}")
        elif not r.ok:
            entry.update(status="butunluk_bozuk", message=f"Zincir bütünlüğü bozuk. {r.reason}")
        elif ref is None or url == ref:
            entry.update(status="tutarli", message="Zincir sağlam; referans düğüm.")
        else:
            ref_r = reports[ref]
            common = min(r.length, ref_r.length)
            if common and r.hash_at.get(common) != ref_r.hash_at.get(common):
                entry.update(
                    status="tutarsiz",
                    message=f"#{common} kaydında referans düğümden farklı hash: zincir ayrışmış.",
                )
            elif r.length < ref_r.length:
                entry.update(
                    status="geride",
                    message=f"Zincir sağlam ama {ref_r.length - r.length} kayıt geride.",
                )
            else:
                entry.update(status="tutarli", message="Zincir sağlam ve referans düğümle aynı.")
        nodes.append(entry)
    return {
        "ok": all(n["status"] == "tutarli" for n in nodes),
        "reference": ref,
        "nodes": nodes,
    }


def verify_nodes(client: LedgerClient) -> dict:
    urls = client.node_urls()
    reports: dict[str, NodeReport] = {}
    for url in urls:
        try:
            v = client.get(url, "/verify")
            reports[url] = NodeReport(True, bool(v["ok"]), int(v["length"]), v.get("reason"))
        except Exception as exc:  # noqa: BLE001
            reports[url] = NodeReport(False, False, 0, type(exc).__name__)
    healthy = [u for u in urls if reports[u].reachable and reports[u].ok]
    lengths = sorted({reports[u].length for u in healthy})
    for url in healthy:
        for n in lengths:
            if 0 < n <= reports[url].length:
                try:
                    rec = client.get(url, f"/records/{n}")
                except Exception as exc:  # noqa: BLE001
                    log.info("kayıt #%s okunamadı (%s): %s", n, url, exc)
                    continue
                if rec:
                    reports[url].hash_at[n] = rec["hash"]
    return compare_nodes(urls, reports)


def record_by_hash(client: LedgerClient, prefix: str) -> dict | None:
    for url in client.node_urls():
        try:
            rec = client.get(url, f"/records/by-hash/{prefix}")
        except Exception as exc:  # noqa: BLE001
            log.info("hash araması başarısız (%s): %s", url, exc)
            continue
        if rec:
            return rec
    return None
