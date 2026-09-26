from fastapi.testclient import TestClient

from ledger.app import NodeConfig, create_app


def test_health(tmp_path):
    app = create_app(NodeConfig("n", "leader", tmp_path, "t"))
    body = TestClient(app).get("/health").json()
    assert body["durum"] == "ok"
