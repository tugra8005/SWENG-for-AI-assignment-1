from fastapi.testclient import TestClient

from ledger.app import app


def test_health():
    body = TestClient(app).get("/health").json()
    assert body["durum"] == "ok"
