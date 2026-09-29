"""Sınıf gösterimi modu: adımlar deterministik durumlar kurar, ``next`` yalnızca geçişi uygular,
``goto`` baştan kurar; aynı adım iki kez kurulunca aynı defter oluşur. Geliştirme uç noktaları
(hesap değiştirici) yalnızca ENV=dev iken vardır."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from mesveret import clock
from mesveret.config import Settings
from mesveret.context import Ctx
from mesveret.db.base import Base
from mesveret.db.models import Proposal, Topic
from mesveret.errors import Conflict, DomainError
from mesveret.main import create_app
from mesveret.services import demo, regulation, seed

DEV = Settings(env="dev", jwt_secret="test-jwt-secret-for-integration-tests-0001",
               shade_key="test-shade", scheduler_enabled=False)


@pytest.fixture
def stage(engine, Session, graph, ledger):
    """Demo sahnesi: ``rebuild`` test veritabanını boşaltır ve tohumlar (asıl yığına dokunmaz)."""

    def rebuild() -> Ctx:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        graph.reset()
        ledger.reset()
        db = Session()
        c = Ctx(db=db, graph=graph, now=seed.SEED_NOW, settings=DEV, ledger=ledger)
        for _ in seed.run(c):
            pass
        db.close()
        return Ctx(db=Session(), graph=graph, now=seed.SEED_NOW, settings=DEV, ledger=ledger)

    db = Session()
    first = Ctx(db=db, graph=graph, now=seed.SEED_NOW, settings=DEV, ledger=ledger)
    yield first, rebuild
    db.rollback()  # açık işlem kalırsa sonraki testin TRUNCATE'i bekler
    db.close()


def fresh(stage):
    ctx = stage[0]
    ctx.db.expire_all()
    return ctx.at(clock.now(ctx.db))


def test_step_three_is_built_from_scratch_with_a_frozen_clock(stage):
    ctx, rebuild = stage
    out = demo.goto(ctx, "3", rebuild=rebuild)
    c = fresh(stage)
    assert clock.is_frozen(c.db) and c.now == seed.SEED_NOW + timedelta(days=1)
    p = c.db.get(Proposal, seed.scenario_ids(c)["istanbul"])
    assert p.status == "ACCEPTED"  # sessiz onayla konu oldu
    topic_id = c.db.execute(select(Topic.id).where(Topic.accepted_proposal_id == p.id)).scalar_one()
    assert [s["path"] for s in out["screens"]] == [f"/konu/{topic_id}", f"/oneri/{p.id}"]
    assert any("sessiz onay süresi doldu" in e for e in out["events"])
    assert out["step"] == "3" and out["next"] == "4"


def test_next_applies_only_the_transition_and_the_last_steps_revert_the_tamper(stage):
    ctx, rebuild = stage
    demo.goto(ctx, "9", rebuild=rebuild)
    out = demo.next_step(fresh(stage), rebuild=rebuild)
    assert out["step"] == "10a"
    assert regulation.verify_state(fresh(stage))["status"] == "farkli"
    out = demo.next_step(fresh(stage), rebuild=rebuild)
    assert out["step"] == "10b" and out["next"] is None
    assert out["events"] == ["Karar Saati #2 açıldı; açılışta geri alındı: yonetmelik_esigi"]
    c = fresh(stage)
    assert regulation.verify_state(c)["status"] == "tutarli"
    with pytest.raises(Conflict):
        demo.next_step(c, rebuild=rebuild)
    assert demo.prev_step(c, rebuild=rebuild)["step"] == "10a"


def test_the_same_step_built_twice_writes_the_same_ledger(stage, ledger):
    """Kimlikler takma addan, tuzlar sunucu anahtarından türetilir; saat donmuştur."""
    ctx, rebuild = stage
    first = demo.goto(ctx, "5", rebuild=rebuild)
    hashes = [r["hash"] for r in ledger.records]
    second = demo.goto(fresh(stage), "5", rebuild=rebuild)
    assert [r["hash"] for r in ledger.records] == hashes and len(hashes) > 500
    assert first["screens"] == second["screens"]


def test_errors_before_start_and_for_unknown_steps(stage):
    ctx, rebuild = stage
    with pytest.raises(Conflict):
        demo.next_step(ctx, rebuild=rebuild)
    with pytest.raises(DomainError):
        demo.goto(ctx, "12", rebuild=rebuild)


def test_dev_endpoints_exist_only_in_dev(ctx, Session, graph, ledger, settings):
    prod = TestClient(create_app(settings=settings.model_copy(update={"env": "prod"}), graph=graph,
                                 ledger=ledger, sessionmaker=Session, with_lifespan=False))
    assert prod.post("/_dev/login-as", json={"nickname": "Hâtif"}).status_code == 404
    assert prod.get("/_dev/demo").status_code == 404
    dev = TestClient(create_app(settings=DEV, graph=graph, ledger=ledger, sessionmaker=Session,
                                with_lifespan=False))
    from tests.integration.world import make_user

    make_user(ctx, "aylin")
    ctx.commit()
    token = dev.post("/_dev/login-as", json={"nickname": "aylin"}).json()["token"]
    assert dev.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["nickname"] == "aylin"
    assert dev.get("/_dev/demo").json() == {"step": None}
