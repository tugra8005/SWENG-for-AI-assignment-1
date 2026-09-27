"""Entegrasyon testleri: gerçek PostgreSQL, bellek içi graf, sahte defter.

PostgreSQL adresi ``TEST_DATABASE_URL`` ile verilir (varsayılan: test yığınının portu).
Neo4j sözleşme testleri ayrıca ``TEST_NEO4J_URL`` ister; yoksa atlanır.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from mesveret import clock
from mesveret.config import Settings
from mesveret.context import Ctx
from mesveret.db.base import Base
from mesveret.graph.memory import InMemoryGraph
from mesveret.main import create_app
from mesveret.services.ledger import FakeLedgerClient
from tests.integration.world import build_world

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://mesveret:mesveret@127.0.0.1:55432/mesveret_test"
)

# Salı 29 Eylül 2026, 10:00 İstanbul
T0 = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB)
    try:
        eng.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL test veritabanına ulaşılamadı: {exc}")
    from mesveret.db import models  # noqa: F401

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def Session(engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(Session):
    s = Session()
    clock.reset_to(s, T0)
    s.commit()
    yield s
    s.close()


@pytest.fixture
def settings():
    return Settings(env="test", jwt_secret="test-jwt-secret-for-integration-tests-0001", shade_key="test-shade",
                    scheduler_enabled=False)


@pytest.fixture
def graph():
    return InMemoryGraph()


@pytest.fixture
def ledger():
    return FakeLedgerClient()


@pytest.fixture
def ctx(db, graph, ledger, settings):
    c = Ctx(db=db, graph=graph, now=T0, settings=settings, ledger=ledger)
    build_world(c)
    return c


@pytest.fixture
def client(ctx, Session, graph, ledger, settings):
    app = create_app(
        settings=settings, graph=graph, ledger=ledger, sessionmaker=Session, with_lifespan=False
    )
    return TestClient(app)


@pytest.fixture(scope="session")
def neo4j_driver():
    url = os.environ.get("TEST_NEO4J_URL")
    if not url:
        pytest.skip("TEST_NEO4J_URL verilmedi; Neo4j sözleşme testleri atlandı.")
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        url, auth=("neo4j", os.environ.get("TEST_NEO4J_PASSWORD", "mesveret-test"))
    )
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j'ye ulaşılamadı: {exc}")
    yield driver
    driver.close()
