"""YALNIZCA GELİŞTİRME: bir düğümün defter kaydını bozar.

"Defteri doğrula" ekranının bozulmayı yakaladığını göstermek içindir.

    python -m ledger.tamper --seq 5                 # içerik değişir, zincir kırılır
    python -m ledger.tamper --seq 5 --mode rechain  # içerik değişir, sonraki hash'ler
                                                    # yeniden hesaplanır: düğüm kendi içinde
                                                    # tutarlı görünür ama liderden ayrışır
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from ledger.chain import payload_hash, record_hash
from ledger.store import TRIGGERS


def _mutate(payload):
    if isinstance(payload, dict):
        return {**payload, "_bozuldu": True}
    return {"_bozuldu": True, "ozgun": payload}


def tamper(db_path: Path, seq: int, mode: str = "payload") -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.executescript(
            "DROP TRIGGER IF EXISTS records_no_update; DROP TRIGGER IF EXISTS records_no_delete;"
        )
        rows = conn.execute(
            "SELECT seq, prev_hash, ts, type, payload FROM records WHERE seq >= ? ORDER BY seq",
            (seq,),
        ).fetchall()
        if not rows or rows[0][0] != seq:
            raise SystemExit(f"Kayıt #{seq} yok.")
        _, prev, _ts, _type, payload_text = rows[0]
        new_payload = _mutate(json.loads(payload_text))
        text = json.dumps(new_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if mode == "payload":
            conn.execute("UPDATE records SET payload = ? WHERE seq = ?", (text, seq))
        elif mode == "rechain":
            for i, (s, _old_prev, ts_i, type_i, payload_i) in enumerate(rows):
                p = new_payload if i == 0 else json.loads(payload_i)
                p_text = text if i == 0 else payload_i
                ph = payload_hash(p)
                h = record_hash(prev, ph, ts_i, type_i)
                conn.execute(
                    "UPDATE records SET prev_hash = ?, payload = ?, payload_hash = ?, hash = ? "
                    "WHERE seq = ?",
                    (prev, p_text, ph, h, s),
                )
                prev = h
        else:
            raise SystemExit("mode 'payload' ya da 'rechain' olmalı.")
    finally:
        conn.executescript(TRIGGERS)
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Geliştirme: defter kaydını boz.")
    parser.add_argument("--seq", type=int, required=True)
    parser.add_argument("--mode", choices=["payload", "rechain"], default="payload")
    parser.add_argument(
        "--db", type=Path,
        default=Path(os.environ.get("DATA_DIR", "./ledger-data")) / "defter.sqlite3",
    )
    args = parser.parse_args()
    tamper(args.db, args.seq, args.mode)
    print(f"UYARI: {args.db} içinde kayıt #{args.seq} bozuldu (mod: {args.mode}).")


if __name__ == "__main__":
    main()
