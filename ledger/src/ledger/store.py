"""Sadece eklenebilir SQLite deposu. UPDATE ve DELETE tetikleyicilerle reddedilir."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ledger.chain import Record

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    seq INTEGER PRIMARY KEY,
    prev_hash TEXT NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_hash ON records(hash);
"""

TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS records_no_update BEFORE UPDATE ON records
BEGIN SELECT RAISE(ABORT, 'defter yalnızca eklenebilir'); END;
CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records
BEGIN SELECT RAISE(ABORT, 'defter yalnızca eklenebilir'); END;
"""

_COLUMNS = "seq, prev_hash, ts, type, payload, payload_hash, hash"


def _row_to_record(row: tuple) -> Record:
    seq, prev, ts, type_, payload, ph, h = row
    return Record(seq, prev, ts, type_, json.loads(payload), ph, h)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._open()

    def _open(self) -> None:
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(SCHEMA + TRIGGERS)

    def append(self, r: Record) -> None:
        payload = json.dumps(r.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self.lock:
            self._conn.execute(
                f"INSERT INTO records ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (r.seq, r.prev_hash, r.ts, r.type, payload, r.payload_hash, r.hash),
            )

    def tip(self) -> Record | None:
        with self.lock:
            row = self._conn.execute(
                f"SELECT {_COLUMNS} FROM records ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return _row_to_record(row) if row else None

    def get(self, seq: int) -> Record | None:
        with self.lock:
            row = self._conn.execute(f"SELECT {_COLUMNS} FROM records WHERE seq = ?", (seq,)).fetchone()
        return _row_to_record(row) if row else None

    def range(self, from_seq: int, limit: int) -> list[Record]:
        with self.lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM records WHERE seq >= ? ORDER BY seq LIMIT ?",
                (from_seq, limit),
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def all(self) -> list[Record]:
        with self.lock:
            rows = self._conn.execute(f"SELECT {_COLUMNS} FROM records ORDER BY seq").fetchall()
        return [_row_to_record(r) for r in rows]

    def find_by_hash(self, prefix: str) -> Record | None:
        prefix = prefix.lower()
        if not prefix or any(c not in "0123456789abcdef" for c in prefix):
            return None
        with self.lock:
            row = self._conn.execute(
                f"SELECT {_COLUMNS} FROM records WHERE hash LIKE ? ORDER BY seq LIMIT 1",
                (prefix + "%",),
            ).fetchone()
        return _row_to_record(row) if row else None

    def wipe(self) -> None:
        """Yalnızca geliştirme sıfırlaması: dosyayı siler ve boş depo açar (DELETE kullanılmaz)."""
        with self.lock:
            self._conn.close()
            for suffix in ("", "-wal", "-shm", "-journal"):
                Path(str(self.path) + suffix).unlink(missing_ok=True)
            self._open()
