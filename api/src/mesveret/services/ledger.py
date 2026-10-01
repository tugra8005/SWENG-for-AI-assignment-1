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
BATCH_SIZE = 200  # bir toplu gönderimdeki en fazla kayıt


# --- istemciler ---------------------------------------------------------------------------------


class LedgerClient(Protocol):
    def append(self, type_: str, payload: Any, ts: str) -> dict: ...
    def append_batch(self, items: list[tuple[str, Any, str]]) -> list[dict]: ...
    def node_urls(self) -> list[str]: ...
    def get(self, url: str, path: str) -> Any: ...
    def reset(self) -> None: ...


class HttpLedgerClient:
    def __init__(self, leader_url: str, node_urls: list[str], token: str, timeout: float = 5.0):
        self.leader_url = leader_url
        self._nodes = node_urls
        self._headers = {"X-Ledger-Token": token}
        self._timeout = timeout
        # Kalıcı bağlantı: her kayıt için yeni TCP bağlantısı açılmaz.
        self._http = httpx.Client(headers=self._headers, timeout=timeout)

    def append(self, type_: str, payload: Any, ts: str) -> dict:
        r = self._http.post(
            f"{self.leader_url}/append", json={"type": type_, "payload": payload, "ts": ts})
        r.raise_for_status()
        return r.json()

    def append_batch(self, items: list[tuple[str, Any, str]]) -> list[dict]:
        """Toplu ekleme: lider kayıtları tek işlemde yazar ve takipçilere tek istekte çoğaltır."""
        r = self._http.post(
            f"{self.leader_url}/append-batch",
            json={"records": [{"type": t, "payload": p, "ts": ts} for t, p, ts in items]},
            timeout=max(self._timeout, 30.0),
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

    def append_batch(self, items: list[tuple[str, Any, str]]) -> list[dict]:
        if self.fail:
            raise ConnectionError("sahte defter kapalı")
        return [self.append(t, p, ts) for t, p, ts in items]

    def node_urls(self) -> list[str]:
        return [self.URL]

    def get(self, url: str, path: str) -> Any:
        if path == "/verify":
            return {"ok": True, "length": len(self.records), "reason": None}
        if path == "/tip":
            last = self.records[-1] if self.records else None
            return {"seq": last["seq"] if last else 0, "hash": last["hash"] if last else "0" * 64,
                    "ts": last["ts"] if last else None, "node_id": "memory"}
        if path.startswith("/records?"):
            q = dict(part.split("=") for part in path.split("?", 1)[1].split("&"))
            start, limit = int(q.get("from_seq", 1)), int(q.get("limit", 100))
            return self.records[start - 1: start - 1 + limit]
        if path.startswith("/records/last-of-type/"):
            type_ = path.rsplit("/", 1)[1]
            return next((r for r in reversed(self.records) if r["type"] == type_), None)
        if path.startswith("/records/of-type/"):
            return self.of_type(path.rsplit("/", 1)[1])
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
    # Zaman damgası azalmaz: geride kalan kayıt bir öncekinin anını alır.
    stamps = []
    for row in pending:
        last_ts = row.ts if last_ts is None or row.ts >= last_ts else last_ts
        stamps.append(last_ts)
    # Toplu gönderim: kayıtlar sırayla, parça parça; bir parça başarısız olursa kalanlar bekler.
    for start in range(0, len(pending), BATCH_SIZE):
        rows, ts_list = pending[start:start + BATCH_SIZE], stamps[start:start + BATCH_SIZE]
        try:
            recs = ctx.ledger.append_batch(
                [(r.type, r.payload, ts.isoformat()) for r, ts in zip(rows, ts_list, strict=True)])
        except Exception as exc:  # noqa: BLE001  (lider erişilemez: kayıtlar bekler)
            log.warning("defter gönderimi başarısız (outbox #%s…): %s", rows[0].id, exc)
            break
        for row, ts, rec in zip(rows, ts_list, recs, strict=True):
            row.ts = ts
            row.sent_at = datetime.now(UTC)
            row.ledger_seq = rec["seq"]
            row.ledger_hash = rec["hash"]
            if row.ref_table and (model := models.get(row.ref_table)):
                key = int(row.ref_id) if row.ref_id and row.ref_id.isdigit() else row.ref_id
                target = db.get(model, key)
                if target is not None:
                    setattr(target, row.ref_attr or "ledger_hash", rec["hash"])
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


def last_of_type(client: LedgerClient, type_: str) -> dict | None:
    """Belirli türdeki en son kayıt (liderden; ulaşılamazsa sıradaki düğümden)."""
    for url in client.node_urls():
        try:
            return client.get(url, f"/records/last-of-type/{type_}")
        except Exception as exc:  # noqa: BLE001
            log.info("son %s kaydı okunamadı (%s): %s", type_, url, exc)
    return None


def records_of_type(client: LedgerClient, type_: str) -> list[dict] | None:
    """Belirli türdeki bütün kayıtlar, sırayla. Hiçbir düğüme ulaşılamazsa ``None``."""
    for url in client.node_urls():
        try:
            return client.get(url, f"/records/of-type/{type_}") or []
        except Exception as exc:  # noqa: BLE001
            log.info("%s kayıtları okunamadı (%s): %s", type_, url, exc)
    return None


# Kayıt türlerinin okunur adları (Meydan'daki "Defterden" kutusu, künye).
RECORD_LABELS = {
    "MESAJ": "Tartışma mesajı",
    "SURUM_EKLENDI": "Mesaj sürümü",
    "ONERI_ACILDI": "Öneri açıldı",
    "ONERI_YAVAS_SERIDE": "Öneri yavaş şeride geçti",
    "ONERI_SONUCU": "Öneri sonuçlandı",
    "KONU_KABUL": "Konu kabul edildi",
    "KONU_YENIDEN_ACILDI": "Konu yeniden açıldı",
    "ICERIK_SILINDI": "İçerik silindi",
    "KAPANIS_METNI": "Kapanış metni",
    "KARAR": "Karar",
    "SERH": "Şerh",
    "PAY_DEGISTI": "Pay değişti",
    "OTURUM_ACILDI": "Karar Saati açıldı",
    "OTURUM_KAPANDI": "Karar Saati kapandı",
    "OY_MUHUR": "Oy mühürlendi",
    "OY_ACILDI": "Oy açıldı",
    "OYLAMA_SONUCU": "Oylama sonucu",
    "YONETMELIK_DEGISTI": "Yönetmelik değişti",
    "YONETMELIK_DURUMU": "Yönetmeliğin hâli",
    "OYLAMASIZ_DEGISIKLIK": "Oylamasız değişiklik",
    "OYLAMASIZ_DEGISIKLIK_GERI_ALINDI": "Oylamasız değişiklik geri alındı",
    "HAVALE_BEKLIYOR": "Havale istendi",
    "HAVALE_KABUL": "Havale kabul edildi",
    "HAVALE_RED": "Havale reddedildi",
    "HAVALE_IADE": "Havale iade edildi",
    "HAVALE_GERI_ALINDI": "Havale geri alındı",
    "HAVALE_YENILENDI": "Havale yenilendi",
    "HAVALE_SURESI_DOLDU": "Havale süresi doldu",
    "MAHZEN_IFSA": "Mahzen başlığı ifşa edildi",
    "GORSEL_EKLENDI": "Görsel eklendi",
}


def record_label(type_: str) -> str:
    return RECORD_LABELS.get(type_, type_.replace("_", " ").capitalize())


def recent(client: LedgerClient, limit: int = 5) -> dict | None:
    """Defterin ucu ve son ``limit`` kayıt, en yenisi önce. Hiçbir düğüme ulaşılamazsa ``None``."""
    for url in client.node_urls():
        try:
            tip = client.get(url, "/tip")
            seq = tip["seq"]
            start = max(1, seq - limit + 1)
            rows = client.get(url, f"/records?from_seq={start}&limit={limit}") if seq else []
        except Exception as exc:  # noqa: BLE001
            log.info("defterin ucu okunamadı (%s): %s", url, exc)
            continue
        return {
            "seq": seq,
            "hash": tip["hash"] if seq else None,
            "records": [{"seq": r["seq"], "type": r["type"], "label": record_label(r["type"]),
                         "ts": r["ts"], "hash": r["hash"]} for r in reversed(rows)],
        }
    return None


def record_at(client: LedgerClient, seq: int) -> dict | None:
    for url in client.node_urls():
        try:
            return client.get(url, f"/records/{seq}")
        except Exception as exc:  # noqa: BLE001
            log.info("#%s kaydı okunamadı (%s): %s", seq, url, exc)
    return None


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
