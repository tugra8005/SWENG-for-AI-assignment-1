"""Geliştirme araçları: sahte saati ilerletme, Karar Saati'ni elle çalıştırma ve yönetmeliği
oylamasız değiştirme (operatörün sessiz değişikliğinin demosu).

``meşveret-dev`` CLI'ı bu fonksiyonları kullanır. Docker'sız yerel geliştirme sunucusu
(``mesveret.devserver``) aynılarını ``/_dev`` uç noktalarından da sunar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mesveret import clock
from mesveret.context import Ctx
from mesveret.domain.regulation import RegulationError, range_violations, validate_value
from mesveret.errors import Conflict, DomainError
from mesveret.services import decision_hour, regulation, scheduler


def advance(ctx: Ctx, target: datetime) -> dict:
    """Saati ilerletir ve aradaki bütün vadesi gelen işleri kendisi işler. Zamanlayıcı kilidini
    saati değiştirmeden önce alır: arka plan iş parçacığı bu sırada bekler, işler bu komutun
    çıktısına düşer."""
    with scheduler.exclusive(ctx.db):
        start = clock.now(ctx.db)
        if target <= start:
            raise DomainError("Hedef an şimdiden sonra olmalı.")
        clock.set_now(ctx.db, target)
        ctx.db.commit()
        done = scheduler.tick(ctx.at(target), target)
    return {"from": start, "to": target, "events": done}


def open_decision_hour(ctx: Ctx, *, scripted: bool) -> dict:
    with scheduler.exclusive(ctx.db):
        return _open_decision_hour(ctx.at(clock.now(ctx.db)), scripted=scripted)


def _open_decision_hour(ctx: Ctx, *, scripted: bool) -> dict:
    scheduler.ensure_state(ctx)
    session = decision_hour.open_session(ctx, scripted=False)
    problems = decision_hour.apply_vote_plan(ctx, session) if scripted else []
    ctx.commit()
    # Kuyrukta kalanlar olgunlaşmamış önerilerdir: sonraki uygun oturuma kayarlar.
    maturing = [
        {"id": q["id"], "title": q["title"], "maturity": q["maturity"]}
        for q in decision_hour.status(ctx)["queued"]
    ]
    return {"session": decision_hour.session_view(ctx, session.id), "problems": problems,
            "maturing": maturing,
            "silent": regulation.session_silent_changes(ctx, session.id, "acilis")}


def close_decision_hour(ctx: Ctx) -> dict:
    """Saati pencere sonuna ilerletir ve oturumu kilidin altında kapatır (bkz. ``advance``)."""
    with scheduler.exclusive(ctx.db):
        session = decision_hour.open_session_row(ctx)
        if session is None:
            raise Conflict("Açık bir Karar Saati oturumu yok.")
        target = max(session.closes_at, clock.now(ctx.db))
        clock.set_now(ctx.db, target)
        ctx.db.commit()
        done = scheduler.tick(ctx.at(target), target)
    return {"session": decision_hour.session_view(ctx, session.id), "events": done,
            "silent": regulation.session_silent_changes(ctx, session.id, "kapanis")}


def tamper_regulation(ctx: Ctx, key: str, value: Any) -> dict:
    """Bir yönetmelik değerini oylamasız, doğrudan graf deposuna yazar: öneri, R8, değişiklik
    geçmişi ve defter kaydı yoktur. Bir operatörün yapabileceğini taklit eder; ``/verify``in
    yönetmelik bütünlüğü denetimi bunu FARKLI olarak göstermelidir. Biçim yine doğrulanır ki
    çalışan uygulama okuyamayacağı bir değerle çökmesin; izinli aralık ise bilerek atlanır.
    """
    old = ctx.graph.articles().get(key)
    if old is None:
        raise DomainError(f"{key} yürürlükte bir yönetmelik maddesi değil.")
    try:
        new = validate_value(key, value)
    except RegulationError as exc:
        raise DomainError(str(exc)) from exc
    ctx.graph.set_article(key, new)
    ctx.invalidate_regulation()
    return {"key": key, "old": old, "new": new, "outside": range_violations(key, new)}
