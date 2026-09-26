"""Hash zinciri.

Kayıt: ``{seq, prev_hash, ts, type, payload, payload_hash, hash}``
- ``payload_hash = sha256(kanonik_json(payload))``
- ``hash = sha256(prev_hash ‖ payload_hash ‖ ts ‖ type)``

``prev_hash`` ve ``payload_hash`` 64 karakter hex, ``ts`` sabit genişlikte UTC ISO-8601
olduğundan düz birleştirme belirsiz değildir. İlk kaydın ``prev_hash`` değeri 64 sıfırdır.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

GENESIS_PREV = "0" * 64


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def format_ts(value: str | datetime) -> str:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        raise ValueError("Zaman damgası saat dilimi içermeli.")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def record_hash(prev_hash: str, p_hash: str, ts: str, type_: str) -> str:
    return hashlib.sha256((prev_hash + p_hash + ts + type_).encode()).hexdigest()


@dataclass(frozen=True)
class Record:
    seq: int
    prev_hash: str
    ts: str
    type: str
    payload: Any
    payload_hash: str
    hash: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Record:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


def build_record(seq: int, prev_hash: str, ts: str | datetime, type_: str, payload: Any) -> Record:
    ts_n = format_ts(ts)
    ph = payload_hash(payload)
    return Record(seq, prev_hash, ts_n, type_, payload, ph, record_hash(prev_hash, ph, ts_n, type_))


def record_problem(r: Record, expected_seq: int, prev_hash: str, prev_ts: str | None) -> str | None:
    """Tek bir kaydın öncekine göre sorunu; sorun yoksa ``None``."""
    if r.seq != expected_seq:
        return f"sıra numarası beklenen {expected_seq} değil"
    if r.prev_hash != prev_hash:
        return "önceki kayda bağlantı (prev_hash) bozuk"
    if r.payload_hash != payload_hash(r.payload):
        return "içerik (payload) değiştirilmiş: payload_hash tutmuyor"
    if r.hash != record_hash(r.prev_hash, r.payload_hash, r.ts, r.type):
        return "kayıt hash'i tutmuyor"
    if prev_ts is not None and r.ts < prev_ts:
        return "zaman damgası geriye gidiyor"
    return None


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    length: int
    tip_hash: str
    first_bad_seq: int | None = None
    reason: str | None = None


def verify_chain(records: Iterable[Record]) -> VerifyResult:
    prev_hash, prev_ts, count = GENESIS_PREV, None, 0
    for r in records:
        problem = record_problem(r, count + 1, prev_hash, prev_ts)
        if problem:
            return VerifyResult(False, count, prev_hash, r.seq, f"Kayıt #{r.seq}: {problem}.")
        prev_hash, prev_ts, count = r.hash, r.ts, count + 1
    return VerifyResult(True, count, prev_hash)
