"""Zamanlayıcı: sahte saate göre vadesi gelen işleri sırayla, her birini kendi vade anında işler.

API içindeki arka plan iş parçacığı ``interval`` saniyede bir ``tick`` çağırır; geliştirme
CLI'ı ``advance-time`` ile aynı fonksiyonu hedef anla çağırır. İki süreç aynı anda çalışırsa
PostgreSQL advisory lock ikincisini bekletir.

Olay kaynakları:
- sessiz onay süresi biten hızlı şerit önerileri,
- rakip metin süresi biten kapanış önerileri,
- penceresi kapanan Karar Saati oturumu,
- haftalık Karar Saati açılışı (``karar_saati`` maddesine göre),
- süresi dolan havaleler (``havale_suresi``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select, text

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import Proposal, SchedulerState
from mesveret.errors import DomainError
from mesveret.services import ledger, proposals

log = logging.getLogger("mesveret.scheduler")

TICK_LOCK_KEY = 515151

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

    edge = delegation.next_expiry(ctx, until)
    if edge is None or edge.expires_at is None:
        return []
    giver, target = delegation.nicknames(ctx, [edge.user_id, edge.target_id])
    area = f" ({edge.area_id})" if edge.area_id else ""
    return [(edge.expires_at, f"havale süresi doldu: {giver} → {target}{area}",
             lambda c, u=edge.user_id, a=edge.area_id: delegation.expire(c, u, a))]


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
    ctx.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": TICK_LOCK_KEY})
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


def start_background(state) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(state.settings.scheduler_interval_seconds):
            db = state.sessionmaker()
            try:
                now = clock.now(db)
                ctx = Ctx(db=db, graph=state.graph, now=now, settings=state.settings,
                          ledger=state.ledger)
                for line in tick(ctx):
                    log.info("işlendi: %s", line)
            except Exception:
                log.exception("zamanlayıcı hatası")
                db.rollback()
            finally:
                db.close()

    threading.Thread(target=loop, name="zamanlayici", daemon=True).start()
    return stop
