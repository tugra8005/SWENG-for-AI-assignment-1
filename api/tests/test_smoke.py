from fastapi.testclient import TestClient

from mesveret.main import create_app


def test_health_reports_missing_dependencies_without_crashing(monkeypatch):
    # Bağımlılıklar yokken sağlık uç noktası çökmeden "eksik" döner.
    monkeypatch.setenv("NEO4J_URL", "bolt://127.0.0.1:1")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/z")
    monkeypatch.setenv("LEDGER_NODE_URLS", "http://127.0.0.1:1")
    from mesveret.config import get_settings
    from mesveret.db.base import get_engine, get_sessionmaker
    from mesveret.graph.driver import get_driver

    for cached in (get_settings, get_engine, get_sessionmaker, get_driver):
        cached.cache_clear()

    client = TestClient(create_app(with_lifespan=False))
    body = client.get("/health").json()
    assert body["durum"] == "eksik"
    assert body["postgres"].startswith("hata")
    assert body["neo4j"].startswith("hata")

    for cached in (get_settings, get_engine, get_sessionmaker, get_driver):
        cached.cache_clear()
