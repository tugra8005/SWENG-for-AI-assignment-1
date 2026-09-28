"""Üç düğümü süreç içinde çalıştırır; HTTP çağrıları TestClient üzerinden yönlendirilir."""

import pytest
from fastapi.testclient import TestClient

from ledger.app import NodeConfig, create_app
from ledger.tamper import tamper

TOKEN = "t"
LEADER = "http://ledger-1"
F2 = "http://ledger-2"
F3 = "http://ledger-3"


class Cluster:
    def __init__(self, tmp_path):
        self.down: set[str] = set()
        self.clients: dict[str, TestClient] = {}

        def factory(url: str):
            if url in self.down:
                raise ConnectionError(url)
            return self.clients[url]

        self.leader_app = create_app(
            NodeConfig("ledger-1", "leader", tmp_path / "1", TOKEN, followers=[F2, F3]),
            client_factory=factory,
        )
        self.f2_app = create_app(
            NodeConfig("ledger-2", "follower", tmp_path / "2", TOKEN, leader=LEADER),
            client_factory=factory,
        )
        self.f3_app = create_app(
            NodeConfig("ledger-3", "follower", tmp_path / "3", TOKEN, leader=LEADER),
            client_factory=factory,
        )
        for url, app in ((LEADER, self.leader_app), (F2, self.f2_app), (F3, self.f3_app)):
            self.clients[url] = TestClient(app, headers={"X-Ledger-Token": TOKEN})

    def append(self, i: int, ts: str | None = None):
        return self.clients[LEADER].post(
            "/append",
            json={"type": "TEST", "payload": {"i": i}, "ts": ts or f"2026-09-29T10:00:{i:02d}Z"},
        )

    def tip(self, url):
        return self.clients[url].get("/tip").json()


@pytest.fixture
def cluster(tmp_path):
    return Cluster(tmp_path)


def test_append_replicates_to_all_followers(cluster):
    for i in range(1, 4):
        assert cluster.append(i).status_code == 200
    tips = {url: cluster.tip(url) for url in (LEADER, F2, F3)}
    assert {t["seq"] for t in tips.values()} == {3}
    assert len({t["hash"] for t in tips.values()}) == 1


def test_append_returns_the_record(cluster):
    body = cluster.append(1).json()
    assert body["seq"] == 1
    assert body["prev_hash"] == "0" * 64
    assert len(body["hash"]) == 64


def test_only_leader_accepts_appends(cluster):
    r = cluster.clients[F2].post("/append", json={"type": "T", "payload": {}, "ts": "2026-09-29T10:00:00Z"})
    assert r.status_code == 403


def test_token_is_required_for_writes(cluster):
    anon = TestClient(cluster.leader_app)
    r = anon.post("/append", json={"type": "T", "payload": {}, "ts": "2026-09-29T10:00:00Z"})
    assert r.status_code == 401


def test_timestamps_must_not_decrease(cluster):
    cluster.append(5)
    assert cluster.append(1).status_code == 409


def test_follower_that_was_down_catches_up_on_next_append(cluster):
    cluster.down.add(F3)
    cluster.append(1)
    cluster.append(2)
    assert cluster.tip(F3)["seq"] == 0
    cluster.down.discard(F3)
    cluster.append(3)
    assert cluster.tip(F3)["seq"] == 3
    assert cluster.tip(F3)["hash"] == cluster.tip(LEADER)["hash"]


def test_follower_can_pull_missing_records(cluster):
    cluster.down.add(F2)
    cluster.append(1)
    cluster.down.discard(F2)
    assert cluster.clients[F2].post("/sync").json()["seq"] == 1


def test_follower_rejects_record_that_does_not_link(cluster):
    cluster.append(1)
    bad = cluster.clients[LEADER].get("/records/1").json()
    bad["seq"] = 2
    r = cluster.clients[F2].post("/replicate", json=bad)
    assert r.status_code == 409


def test_verify_reports_ok_and_lookup_by_hash(cluster):
    for i in range(1, 4):
        cluster.append(i)
    v = cluster.clients[F3].get("/verify").json()
    assert v["ok"] and v["length"] == 3
    h = cluster.tip(LEADER)["hash"]
    assert cluster.clients[F2].get(f"/records/by-hash/{h[:10]}").json()["seq"] == 3


def test_tampered_payload_breaks_integrity_on_that_node_only(cluster, tmp_path):
    for i in range(1, 6):
        cluster.append(i)
    tamper(tmp_path / "2" / "defter.sqlite3", seq=3, mode="payload")
    v2 = cluster.clients[F2].get("/verify").json()
    assert not v2["ok"]
    assert v2["first_bad_seq"] == 3
    assert cluster.clients[F3].get("/verify").json()["ok"]


def test_rechained_tamper_passes_local_verify_but_diverges_from_leader(cluster, tmp_path):
    for i in range(1, 6):
        cluster.append(i)
    tamper(tmp_path / "2" / "defter.sqlite3", seq=3, mode="rechain")
    assert cluster.clients[F2].get("/verify").json()["ok"]
    assert cluster.tip(F2)["hash"] != cluster.tip(LEADER)["hash"]
    assert cluster.tip(F2)["seq"] == cluster.tip(LEADER)["seq"]


def test_last_record_of_a_type_is_served_by_every_node(cluster):
    c = cluster.clients[LEADER]
    for i, type_ in enumerate(("YONETMELIK_DURUMU", "TEST", "YONETMELIK_DURUMU", "TEST"), start=1):
        c.post("/append", json={"type": type_, "payload": {"i": i}, "ts": f"2026-09-29T10:00:{i:02d}Z"})
    for url in (LEADER, F2, F3):
        rec = cluster.clients[url].get("/records/last-of-type/YONETMELIK_DURUMU").json()
        assert (rec["seq"], rec["payload"]) == (3, {"i": 3})
    assert c.get("/records/last-of-type/YOK").status_code == 404


def test_all_records_of_a_type_in_order(cluster):
    c = cluster.clients[LEADER]
    for i, type_ in enumerate(("OYLAMASIZ_DEGISIKLIK", "TEST", "OYLAMASIZ_DEGISIKLIK"), start=1):
        c.post("/append", json={"type": type_, "payload": {"i": i}, "ts": f"2026-09-29T10:00:{i:02d}Z"})
    for url in (LEADER, F2, F3):
        recs = cluster.clients[url].get("/records/of-type/OYLAMASIZ_DEGISIKLIK").json()
        assert [(r["seq"], r["payload"]) for r in recs] == [(1, {"i": 1}), (3, {"i": 3})]
    assert c.get("/records/of-type/YOK").json() == []
