"""Zamanlayıcı: sahte saate göre vadesi gelen işleri sırayla, her birini kendi vade anında işler.

API içindeki arka plan iş parçacığı ``interval`` saniyede bir ``tick`` çağırır; geliştirme
CLI'ı ``advance-time`` ile aynı fonksiyonu hedef anla çağırır.

Kilit: tek bir PostgreSQL advisory lock (oturum düzeyinde, ayrı bir bağlantıda tutulur; işlerin
içindeki ara commit'ler onu bırakmaz). ``tick`` bu kilidi alır. Zamanı değiştiren geliştirme
komutları (``advance-time``, ``run-karar-saati``, ``seed``) kilidi saati değiştirmeden önce alır
ve komut bitene kadar tutar; aradaki bütün vadesi gelen işleri kendileri işler, çıktıları da
komutun çıktısına düşer. Arka plan iş parçacığı kilidi beklemez, dener: alamazsa o adımı atlar
ve saati ancak kilidi aldıktan sonra okur. Böylece iki süreç aynı işi işleyemez; yine de her iş
idempotenttir (durumu denetler, bir kez yazar).

Olay kaynakları:
- sessiz onay süresi biten hızlı şerit önerileri,
- rakip metin süresi biten kapanış önerileri,
- penceresi kapanan Karar Saati oturumu,
- haftalık Karar Saati açılışı (``karar_saati`` maddesine göre),
- süresi dolan havaleler (``havale_suresi``),
- kabul süresi dolan bekleyen havaleler (``havale_kabul_suresi``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import Proposal, SchedulerState
from mesveret.errors import DomainError
from mesveret.services import ledger, proposals

log = logging.getLogger("mesveret.scheduler")

TICK_LOCK_KEY = 515151
_held = threading.local()  # bu iş parçacığının tuttuğu kilitler (iç içe alım için)


def _engine(bind: Engine | Session) -> Engine:
    return bind.get_bind() if isinstance(bind, Session) else bind


@contextmanager
def exclusive(bind: Engine | Session, *, wait: bool = True) -> Iterator[bool]:
    """Zamanlayıcı kilidi. ``wait=False`` ise kilit başkasındaysa beklemez, ``False`` verir.

    Kilit ayrı bir bağlantıda oturum düzeyinde tutulur: kilidi alan kodun kendi oturumundaki
    commit'ler kilidi bırakmaz. Aynı iş parçacığı kilidi iç içe alabilir (CLI komutu kilidi
    tutarken ``tick`` çağırır)."""
    engine = _engine(bind)
    key = str(engine.url)
    depth: dict[str, int] = getattr(_held, "depth", None) or {}
    _held.depth = depth
    if depth.get(key):
        depth[key] += 1
        try:
            yield True
        finally:
            depth[key] -= 1
        return
    conn = engine.connect()
    try:
        if wait:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": TICK_LOCK_KEY})
            got = True
        else:
            got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                    {"k": TICK_LOCK_KEY}).scalar())
        conn.commit()  # oturum düzeyindeki kilit commit'ten sonra da sürer
    except Exception:
        conn.invalidate()
        conn.close()
        raise
    if not got:
        conn.close()
        yield False
        return
    depth[key] = 1
    try:
        yield True
    finally:
        depth[key] = 0
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": TICK_LOCK_KEY})
            conn.commit()
        except Exception:  # noqa: BLE001  (bağlantı düşerse kilit de düşer)
            conn.invalidate()
        finally:
            conn.close()

Event = tuple[datetime, str, Callable[[Ctx], None]]


def _proposal_events(ctx: Ctx, until: datetime) -> list[Event]:
    events: list[Event] = []
    for status, label, handler in (
        ("SILENT", "sessiz onay süresi doldu", proposals.end_silent_period),
        ("RIVAL_PERIOD", "rakip metin süresi doldu", proposals.end_rival_period),
    ):
        row = ctx.db.execute(
            select(Proposal).where(Proposal.status == status, Proposal.deadline_at <= until)
            .order_by(Proposal.deadline_at, Proposal.id).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            pid = row.id

            def run(c: Ctx, pid=pid, handler=handler) -> None:
                p = proposals.get_proposal(c, pid)
                try:
                    handler(c, p)
                except DomainError as exc:
                    proposals.reject(c, p, f"Uygulanamadı: {exc.message}")

            events.append((row.deadline_at, f"#{pid}: {label}", run))
    return events


def _delegation_events(ctx: Ctx, until: datetime) -> list[Event]:
    from mesveret.services import delegation

    events: list[Event] = []
    edge = delegation.next_expiry(ctx, until)
    if edge is not None and edge.expires_at is not None:
        giver, target = delegation.nicknames(ctx, [edge.user_id, edge.target_id])
        area = f" ({edge.area_id})" if edge.area_id else ""
        events.append((edge.expires_at, f"havale süresi doldu: {giver} → {target}{area}",
                       lambda c, u=edge.user_id, a=edge.area_id: delegation.expire(c, u, a)))
    req = delegation.next_request_expiry(ctx, until)
    if req is not None:
        giver, target = delegation.nicknames(ctx, [req.giver_id, req.target_id])
        area = f" ({req.area_id})" if req.area_id else ""
        events.append((req.decide_by, f"havale kabul süresi doldu: {giver} → {target}{area}",
                       lambda c, rid=req.id: delegation.expire_request(c, rid)))
    return events


def _decision_hour_events(ctx: Ctx, until: datetime, last: datetime | None) -> list[Event]:
    from mesveret.services import decision_hour

    return decision_hour.due_events(ctx, until, last)


def ensure_state(ctx: Ctx) -> SchedulerState:
    """Zamanlayıcının başlangıç anını kurar (tohum ve testler bunu kurulum anında çağırır)."""
    return _state(ctx)


def _state(ctx: Ctx) -> SchedulerState:
    st = ctx.db.get(SchedulerState, 1)
    if st is None:
        st = SchedulerState(id=1, last_tick_at=ctx.now)
        ctx.db.add(st)
        ctx.db.flush()
    return st


def tick(ctx: Ctx, until: datetime | None = None) -> list[str]:
    """``until`` anına kadar vadesi gelen işleri işler; işlenenlerin açıklamalarını döner."""
    until = until or ctx.now
    with exclusive(ctx.db):
        return _tick_locked(ctx, until)


def _tick_locked(ctx: Ctx, until: datetime) -> list[str]:
    st = _state(ctx)
    done: list[str] = []
    while True:
        # Aynı andaki olaylarda havale dolumu önce gelir (min ilk en küçüğü seçer): o anda açılan
        # oturumun anlık görüntüsü zaten bitişi gelmiş havaleyi almaz.
        events = (_delegation_events(ctx, until) + _proposal_events(ctx, until)
                  + _decision_hour_events(ctx, until, st.last_tick_at))
        if not events:
            break
        when, label, run = min(events, key=lambda e: e[0])
        run(ctx.at(when))
        st.last_tick_at = max(st.last_tick_at or when, when)
        ctx.db.flush()
        done.append(f"{when.isoformat()} {label}")
    st.last_tick_at = max(st.last_tick_at or until, until)
    ctx.db.commit()
    ledger.flush(ctx)
    return done


def background_tick(sessionmaker, graph, settings, ledger_client) -> list[str] | None:
    """Arka plan iş parçacığının bir adımı. Kilit başkasındaysa (bir geliştirme komutu zamanı
    ilerletiyor) hiçbir şey yapmaz ve ``None`` döner; o komut aradaki işleri kendisi işler. Saat
    kilit alındıktan sonra okunur."""
    db = sessionmaker()
    try:
        with exclusive(db, wait=False) as got:
            if not got:
                return None
            ctx = Ctx(db=db, graph=graph, now=clock.now(db), settings=settings,
                      ledger=ledger_client)
            return tick(ctx)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def start_background(state) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(state.settings.scheduler_interval_seconds):
            try:
                lines = background_tick(state.sessionmaker, state.graph, state.settings,
                                        state.ledger)
            except Exception:
                log.exception("zamanlayıcı hatası")
                continue
            if lines is None:
                log.debug("zamanlayıcı kilidi bir geliştirme komutunda; adım atlandı")
            for line in lines or []:
                log.info("işlendi: %s", line)

    threading.Thread(target=loop, name="zamanlayici", daemon=True).start()
    return stop
