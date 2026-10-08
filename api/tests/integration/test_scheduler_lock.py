"""Zamanlayıcı kilidi ve zamanlanmış işlerin idempotentliği.

- Zamanı ilerleten geliştirme komutu kilidi saati değiştirmeden önce alır ve tutar: arka plan
  iş parçacığı o sırada hiçbir şey işlemez, aradaki bütün işler komutun çıktısına düşer.
- Her zamanlanmış iş ikinci kez çalıştırılınca hiçbir şey yazmaz.
- İki süreç aynı anı aynı anda işlese de her iş deftere bir kez yazılır.
"""

import threading
from collections import Counter
from datetime import timedelta

from sqlalchemy import func, select

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import DecisionSession, LedgerOutbox
from mesveret.services import decision_hour, delegation, devtools, jobs, proposals, scheduler
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import open_topic, post, reload
from tests.integration.world import make_user

DAY = timedelta(days=1)


def outbox(db) -> Counter:
    db.expire_all()
    rows = db.execute(select(LedgerOutbox.type, func.count()).group_by(LedgerOutbox.type)).all()
    return Counter(dict(rows))


def due_world(ctx):
    """Sekiz gün içinde vadesi gelen her türden iş: havale dolumu, kabul süresi, sessiz onay,
    rakip metin süresi, haftalık Karar Saati açılışı ve kapanışı."""
    a, b, c = make_user(ctx, "aylin"), make_user(ctx, "baris"), make_user(ctx, "ceren")
    ctx.graph.set_delegation(a.id, b.id, None, ctx.now - 178 * DAY, ctx.now + 2 * DAY)
    request = delegation.request_delegation(ctx, c, "baris", "ulasim")
    silent = proposals.open_proposal(ctx, a, ProposalInput(
        type="KONU", addressee="takvim", title="Kitap takası", body="Ayda bir kitap takası.", area_id="edebiyat",
        scope_id="genel"))
    topic = open_topic(ctx, a, title="Park saatleri", area="kent")
    post(ctx, b, topic, "Bence 22:00.")
    rival = proposals.open_proposal(ctx, a, ProposalInput(
        type="KAPANIS", target_topic_id=topic.id, body="Parklar 20:00'de kapansın."))
    scheduler.ensure_state(ctx)
    ctx.commit()
    assert (silent.status, rival.status, request.status) == ("SILENT", "RIVAL_PERIOD", "PENDING")
    return {"request": request, "silent": silent, "rival": rival, "giver": a}


EXPECTED = {"HAVALE_SURESI_DOLDU": 1, "HAVALE_RED": 1, "OTURUM_ACILDI": 1, "OTURUM_KAPANDI": 1}


def test_every_scheduled_job_is_idempotent(ctx):
    w = due_world(ctx)
    later = ctx.at(ctx.now + 8 * DAY)

    def twice(job):
        job()
        later.db.flush()
        first = outbox(later.db)
        job()
        later.db.flush()
        assert outbox(later.db) == first  # ikinci çalıştırma deftere yazmaz
        return first

    before = outbox(later.db)
    after = twice(lambda: delegation.expire(later, w["giver"].id, None))
    assert after["HAVALE_SURESI_DOLDU"] == before["HAVALE_SURESI_DOLDU"] + 1
    after = twice(lambda: delegation.expire_request(later, w["request"].id))
    assert after["HAVALE_RED"] == before["HAVALE_RED"] + 1
    twice(lambda: proposals.end_silent_period(later, reload(later, w["silent"])))
    assert reload(later, w["silent"]).status == "ACCEPTED"
    twice(lambda: proposals.end_rival_period(later, reload(later, w["rival"])))
    assert reload(later, w["rival"]).status == "QUEUED"

    occ = decision_hour.next_occurrence(ctx.now, later.reg.decision_hour())
    at_open = later.at(occ)
    twice(lambda: jobs.OpenDecisionHour(occ).run(at_open))
    [session] = later.db.execute(select(DecisionSession)).scalars().all()
    at_close = later.at(session.closes_at)
    twice(lambda: jobs.CloseDecisionHour(session.closes_at, session.id).run(at_close))
    assert session.status == "CLOSED"


def test_a_second_tick_over_the_same_interval_does_nothing(ctx):
    due_world(ctx)
    target = ctx.now + 8 * DAY
    first = scheduler.tick(ctx.at(target), target)
    snapshot = outbox(ctx.db)
    assert scheduler.tick(ctx.at(target), target) == []
    assert outbox(ctx.db) == snapshot
    assert {k: snapshot[k] for k in EXPECTED} == EXPECTED
    assert any(line.endswith("havale kabul süresi doldu: ceren → baris (ulasim)") for line in first)


def test_two_processes_ticking_at_once_write_each_job_once(ctx, Session, graph, ledger, settings):
    w = due_world(ctx)
    target = ctx.now + 8 * DAY
    before = outbox(ctx.db)
    barrier = threading.Barrier(2)
    results: list[list[str]] = [[], []]
    errors: list[BaseException] = []

    def run(i: int) -> None:
        db = Session()
        try:
            c = Ctx(db=db, graph=graph, now=target, settings=settings, ledger=ledger)
            barrier.wait()
            results[i] = scheduler.tick(c, target)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    lines = results[0] + results[1]
    assert len(lines) == len(set(lines)) and lines  # her iş bir kez, tek bir tarafta
    assert [] in results  # kilidi ikinci alan taraf için iş kalmamıştı
    after = outbox(ctx.db)
    assert {k: after[k] - before[k] for k in EXPECTED} == EXPECTED
    assert after["ONERI_SONUCU"] - before["ONERI_SONUCU"] == 1  # sessiz onayla kabul
    ctx.db.expire_all()
    assert reload(ctx, w["silent"]).status == "ACCEPTED"


def test_background_step_waits_while_a_dev_command_holds_the_lock(ctx, Session, graph, ledger,
                                                                  settings):
    due_world(ctx)
    clock.set_now(ctx.db, ctx.now + 8 * DAY)  # komut saati ilerletti, işler vadesinde
    ctx.db.commit()
    before = outbox(ctx.db)
    seen: list = []

    def background() -> None:
        seen.append(scheduler.background_tick(Session, graph, settings, ledger))

    with scheduler.exclusive(ctx.db):
        t = threading.Thread(target=background)
        t.start()
        t.join(timeout=30)
        assert seen == [None]  # beklemedi, adımı atladı
        assert outbox(ctx.db) == before
    t = threading.Thread(target=background)
    t.start()
    t.join(timeout=60)
    assert seen[1] and outbox(ctx.db)["HAVALE_RED"] == before["HAVALE_RED"] + 1


def test_advance_time_processes_everything_itself(ctx, Session, graph, ledger, settings,
                                                 monkeypatch):
    """advance-time saati değiştirdikten sonra arka plan adımı araya giremez; işler komutun
    çıktısına düşer (senaryo 13 ve 15)."""
    due_world(ctx)
    real_tick = scheduler.tick
    background: list = []

    def tick_with_intruder(c, until=None):
        # Saat ilerletildi ve commit edildi; tam bu anda arka plan iş parçacığı uyanıyor.
        monkeypatch.setattr(scheduler, "tick", real_tick)
        t = threading.Thread(target=lambda: background.append(
            scheduler.background_tick(Session, graph, settings, ledger)))
        t.start()
        t.join(timeout=30)
        return real_tick(c, until)

    monkeypatch.setattr(scheduler, "tick", tick_with_intruder)
    out = devtools.advance(ctx, ctx.now + 8 * DAY)
    assert background == [None]
    assert "havale kabul süresi doldu: ceren → baris (ulasim)" in " | ".join(out["events"])
    assert any("haftalık Karar Saati açıldı" in line for line in out["events"])
    assert any("Karar Saati #1 kapandı" in line for line in out["events"])
