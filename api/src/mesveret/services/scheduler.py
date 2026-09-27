"""Zamanlayıcı: sahte saate göre vadesi gelen işleri sırayla işler.

API içindeki arka plan iş parçacığı ``interval`` saniyede bir ``tick`` çağırır; geliştirme
CLI'ı ``advance-time`` ile aynı fonksiyonu hedef anla çağırır. İki süreç aynı anda çalışırsa
PostgreSQL advisory lock ikincisini bekletir.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from sqlalchemy import text

from mesveret import clock
from mesveret.context import Ctx
from mesveret.services import ledger

log = logging.getLogger("mesveret.scheduler")

TICK_LOCK_KEY = 515151


def tick(ctx: Ctx, until: datetime | None = None) -> list[str]:
    """``until`` anına kadar vadesi gelen işleri işler; işlenenlerin açıklamalarını döner."""
    until = until or ctx.now
    ctx.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": TICK_LOCK_KEY})
    done: list[str] = []
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
                tick(ctx)
            except Exception:
                log.exception("zamanlayıcı hatası")
                db.rollback()
            finally:
                db.close()

    threading.Thread(target=loop, name="zamanlayici", daemon=True).start()
    return stop
