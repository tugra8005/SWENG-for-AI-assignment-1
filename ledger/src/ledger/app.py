"""Defter düğümü HTTP servisi.

- Lider (ledger-1) ``/append`` ile kayıt alır, yazar ve takipçilere ``/replicate`` ile iter.
- Takipçi bir kaydı yalnızca kendi ucuna bağlanıyorsa ve hash'leri tutuyorsa ekler.
  Geride kalan takipçiye lider eksik kayıtları iter; takipçi de periyodik olarak ``/sync``
  ile liderden çeker.
- ``/verify`` zinciri baştan yeniden hesaplar. Okuma uç noktaları herkese açıktır; yazma
  uç noktaları ``X-Ledger-Token`` ister.

Oylama algoritması (Raft vb.) ve lider devri yoktur; bkz. DESIGN.md §11 ve §15.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from ledger.chain import GENESIS_PREV, Record, build_record, format_ts, record_problem, verify_chain
from ledger.store import Store

log = logging.getLogger("ledger")

SYNC_INTERVAL_SECONDS = 5.0


@dataclass
class NodeConfig:
    node_id: str
    role: str  # "leader" | "follower"
    data_dir: Path
    token: str
    followers: list[str] = field(default_factory=list)
    leader: str | None = None
    dev_mode: bool = False

    @classmethod
    def from_env(cls) -> NodeConfig:
        return cls(
            node_id=os.environ.get("NODE_ID", "ledger-local"),
            role=os.environ.get("ROLE", "leader"),
            data_dir=Path(os.environ.get("DATA_DIR", "./ledger-data")),
            token=os.environ.get("LEDGER_TOKEN", "dev-ledger-token"),
            followers=[u for u in os.environ.get("FOLLOWER_URLS", "").split(",") if u],
            leader=os.environ.get("LEADER_URL") or None,
            dev_mode=os.environ.get("DEV_MODE", "1") == "1",
        )


class AppendIn(BaseModel):
    type: str
    payload: Any
    ts: str


class RecordIn(BaseModel):
    seq: int
    prev_hash: str
    ts: str
    type: str
    payload: Any
    payload_hash: str
    hash: str


ClientFactory = Callable[[str], httpx.Client]


def create_app(cfg: NodeConfig, client_factory: ClientFactory | None = None) -> FastAPI:
    store = Store(cfg.data_dir / "defter.sqlite3")
    stop = threading.Event()

    def default_factory(url: str) -> httpx.Client:
        return httpx.Client(base_url=url, timeout=3.0, headers={"X-Ledger-Token": cfg.token})

    factory = client_factory or default_factory

    def require_token(x_ledger_token: str | None = Header(default=None)) -> None:
        if x_ledger_token != cfg.token:
            raise HTTPException(401, "Geçersiz defter anahtarı.")

    def tip_dict() -> dict:
        tip = store.tip()
        return {"seq": tip.seq if tip else 0, "hash": tip.hash if tip else GENESIS_PREV,
                "ts": tip.ts if tip else None, "node_id": cfg.node_id}

    def apply(rec: Record) -> str | None:
        """Takipçide bir kaydı uygular; sorun varsa açıklamasını döner."""
        with store.lock:
            tip = store.tip()
            tip_seq = tip.seq if tip else 0
            if rec.seq <= tip_seq:
                existing = store.get(rec.seq)
                return None if existing and existing.hash == rec.hash else "çatışan kayıt"
            problem = record_problem(
                rec, tip_seq + 1, tip.hash if tip else GENESIS_PREV, tip.ts if tip else None
            )
            if problem:
                return problem
            store.append(rec)
            return None

    def push_to(url: str, rec: Record) -> None:
        client = factory(url)
        r = client.post("/replicate", json=rec.to_dict())
        if r.status_code != 409:
            r.raise_for_status()
            return
        follower_tip = r.json().get("detail", {}).get("tip_seq")
        if follower_tip is None or follower_tip >= rec.seq:
            raise RuntimeError(f"{url} kaydı reddetti: {r.text}")
        for missing in store.range(follower_tip + 1, rec.seq - follower_tip):
            client.post("/replicate", json=missing.to_dict()).raise_for_status()

    def replicate(rec: Record) -> None:
        for url in cfg.followers:
            try:
                push_to(url, rec)
            except Exception as exc:  # noqa: BLE001  (takipçi daha sonra yetişir)
                log.warning("çoğaltma başarısız %s: %s", url, exc)

    def sync_from_leader() -> dict:
        if cfg.leader is None:
            return tip_dict()
        client = factory(cfg.leader)
        while True:
            tip = store.tip()
            batch = client.get("/records", params={"from_seq": (tip.seq if tip else 0) + 1,
                                                   "limit": 500}).json()
            if not batch:
                break
            for d in batch:
                problem = apply(Record.from_dict(d))
                if problem:
                    raise HTTPException(409, {"reason": problem, "tip_seq": tip_dict()["seq"]})
        return tip_dict()

    def sync_loop() -> None:
        while not stop.wait(SYNC_INTERVAL_SECONDS):
            try:
                sync_from_leader()
            except Exception as exc:  # noqa: BLE001
                log.info("eşitleme başarısız: %s", exc)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if cfg.role == "follower":
            threading.Thread(target=sync_loop, daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title=f"Meşveret defteri ({cfg.node_id})", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"durum": "ok", "dugum": cfg.node_id, "rol": cfg.role}

    @app.get("/tip")
    def tip() -> dict:
        return tip_dict()

    @app.post("/append", dependencies=[Depends(require_token)])
    def append(body: AppendIn) -> dict:
        if cfg.role != "leader":
            raise HTTPException(403, "Yalnızca lider düğüm kayıt kabul eder.")
        with store.lock:
            tip = store.tip()
            try:
                ts = format_ts(body.ts)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if tip and ts < tip.ts:
                raise HTTPException(409, "Zaman damgası son kayıttan önce olamaz.")
            rec = build_record(
                (tip.seq if tip else 0) + 1, tip.hash if tip else GENESIS_PREV, ts,
                body.type, body.payload,
            )
            store.append(rec)
            replicate(rec)
        return rec.to_dict()

    @app.post("/replicate", dependencies=[Depends(require_token)])
    def replicate_in(body: RecordIn) -> dict:
        rec = Record(**body.model_dump())
        problem = apply(rec)
        if problem:
            raise HTTPException(409, {"reason": problem, "tip_seq": tip_dict()["seq"]})
        return tip_dict()

    @app.post("/sync", dependencies=[Depends(require_token)])
    def sync() -> dict:
        return sync_from_leader()

    @app.get("/records")
    def records(from_seq: int = 1, limit: int = 100) -> list[dict]:
        return [r.to_dict() for r in store.range(from_seq, min(limit, 1000))]

    @app.get("/records/by-hash/{prefix}")
    def by_hash(prefix: str) -> dict:
        rec = store.find_by_hash(prefix)
        if rec is None:
            raise HTTPException(404, "Bu hash ile başlayan kayıt yok.")
        return rec.to_dict()

    @app.get("/records/last-of-type/{type_}")
    def last_of_type(type_: str) -> dict:
        rec = store.last_of_type(type_)
        if rec is None:
            raise HTTPException(404, "Bu türde kayıt yok.")
        return rec.to_dict()

    @app.get("/records/of-type/{type_}")
    def of_type(type_: str) -> list[dict]:
        return [r.to_dict() for r in store.of_type(type_)]

    @app.get("/records/{seq}")
    def record(seq: int) -> dict:
        rec = store.get(seq)
        if rec is None:
            raise HTTPException(404, "Kayıt yok.")
        return rec.to_dict()

    @app.get("/verify")
    def verify() -> dict:
        result = verify_chain(store.all())
        return {"node_id": cfg.node_id, "ok": result.ok, "length": result.length,
                "tip_hash": result.tip_hash, "first_bad_seq": result.first_bad_seq,
                "reason": result.reason}

    @app.post("/_dev/reset", dependencies=[Depends(require_token)])
    def dev_reset() -> dict:
        if not cfg.dev_mode:
            raise HTTPException(403, "Sıfırlama yalnızca geliştirme ortamında.")
        store.wipe()
        if cfg.role == "leader":
            for url in cfg.followers:
                try:
                    factory(url).post("/_dev/reset").raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    log.warning("takipçi sıfırlanamadı %s: %s", url, exc)
        return tip_dict()

    app.state.store = store
    return app


def app_from_env() -> FastAPI:
    """``uvicorn --factory ledger.app:app_from_env``"""
    logging.basicConfig(level=logging.INFO)
    return create_app(NodeConfig.from_env())
