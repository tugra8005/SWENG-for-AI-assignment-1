import hashlib
import sqlite3
from dataclasses import replace

import pytest

from ledger.chain import GENESIS_PREV, build_record, format_ts, payload_hash, verify_chain
from ledger.store import Store


def make_chain(n: int):
    records = []
    prev = GENESIS_PREV
    for i in range(1, n + 1):
        r = build_record(i, prev, f"2026-09-29T10:00:0{i}+03:00", "TEST", {"i": i, "metin": "ş"})
        records.append(r)
        prev = r.hash
    return records


def test_hash_formula_matches_the_spec():
    r = build_record(1, GENESIS_PREV, "2026-09-29T07:00:00Z", "ICERIK", {"a": 1})
    ph = hashlib.sha256(b'{"a":1}').hexdigest()
    assert r.payload_hash == ph
    assert r.ts == "2026-09-29T07:00:00.000000Z"
    assert r.hash == hashlib.sha256(
        (GENESIS_PREV + ph + r.ts + "ICERIK").encode()
    ).hexdigest()


def test_timestamps_are_normalised_to_fixed_width_utc():
    assert format_ts("2026-09-29T10:00:00+03:00") == "2026-09-29T07:00:00.000000Z"
    assert len(format_ts("2026-09-29T10:00:00.5+03:00")) == 27


def test_first_record_links_to_zero_hash():
    assert make_chain(1)[0].prev_hash == "0" * 64


def test_valid_chain_verifies():
    result = verify_chain(make_chain(5))
    assert result.ok
    assert result.length == 5


def test_changed_payload_is_detected():
    chain = make_chain(5)
    chain[2] = replace(chain[2], payload={"i": 3, "metin": "değişti"})
    result = verify_chain(chain)
    assert not result.ok
    assert result.first_bad_seq == 3
    assert "içerik" in result.reason


def test_recomputed_payload_hash_without_rechaining_is_detected():
    chain = make_chain(5)
    new_payload = {"i": 3, "metin": "değişti"}
    chain[2] = replace(chain[2], payload=new_payload, payload_hash=payload_hash(new_payload))
    result = verify_chain(chain)
    assert not result.ok
    assert result.first_bad_seq == 3


def test_broken_link_is_detected():
    chain = make_chain(5)
    rehashed = build_record(3, "f" * 64, chain[2].ts, chain[2].type, chain[2].payload)
    chain[2] = rehashed
    result = verify_chain(chain)
    assert not result.ok
    assert result.first_bad_seq == 3


def test_sequence_gap_is_detected():
    chain = make_chain(5)
    del chain[1]
    assert verify_chain(chain).first_bad_seq == 3


def test_decreasing_timestamp_is_detected():
    chain = make_chain(2)
    bad = build_record(3, chain[1].hash, "2026-09-29T09:00:00+03:00", "TEST", {})
    result = verify_chain([*chain, bad])
    assert not result.ok
    assert result.first_bad_seq == 3


def test_store_is_append_only(tmp_path):
    store = Store(tmp_path / "defter.sqlite3")
    for r in make_chain(3):
        store.append(r)
    with pytest.raises(sqlite3.DatabaseError):
        store._conn.execute("UPDATE records SET payload = '{}' WHERE seq = 1")
    with pytest.raises(sqlite3.DatabaseError):
        store._conn.execute("DELETE FROM records WHERE seq = 1")
    assert store.tip().seq == 3
    assert verify_chain(store.all()).ok


def test_store_lookup_by_hash_prefix(tmp_path):
    store = Store(tmp_path / "defter.sqlite3")
    chain = make_chain(3)
    for r in chain:
        store.append(r)
    assert store.find_by_hash(chain[1].hash[:12]).seq == 2
    assert store.find_by_hash("zzzz") is None
