"""Geliştirme araçları: sahte saati ilerletme ve Karar Saati'ni elle çalıştırma.

``meşveret-dev`` CLI'ı bu fonksiyonları kullanır. Docker'sız yerel geliştirme sunucusu
(``mesveret.devserver``) aynılarını ``/_dev`` uç noktalarından da sunar.
"""

from __future__ import annotations

from datetime import datetime

from mesveret import clock
from mesveret.context import Ctx
from mesveret.errors import Conflict, DomainError
from mesveret.services import decision_hour, scheduler


def advance(ctx: Ctx, target: datetime) -> dict:
    start = clock.now(ctx.db)
    if target <= start:
        raise DomainError("Hedef an şimdiden sonra olmalı.")
    clock.set_now(ctx.db, target)
    ctx.db.commit()
    done = scheduler.tick(ctx.at(target), target)
    return {"from": start, "to": target, "events": done}


def open_decision_hour(ctx: Ctx, *, scripted: bool) -> dict:
    scheduler.ensure_state(ctx)
    session = decision_hour.open_session(ctx, scripted=False)
    problems = decision_hour.apply_vote_plan(ctx, session) if scripted else []
    ctx.commit()
    return {"session": decision_hour.session_view(ctx, session.id), "problems": problems}


def close_decision_hour(ctx: Ctx) -> dict:
    session = decision_hour.open_session_row(ctx)
    if session is None:
        raise Conflict("Açık bir Karar Saati oturumu yok.")
    target = max(session.closes_at, clock.now(ctx.db))
    clock.set_now(ctx.db, target)
    ctx.db.commit()
    done = scheduler.tick(ctx.at(session.closes_at), session.closes_at)
    return {"session": decision_hour.session_view(ctx, session.id), "events": done}
