"""Geliştirme CLI'ı: ``meşveret-dev`` (ASCII takma adı ``mesveret-dev``).

Yalnızca ``ENV=dev`` iken çalışır. Demo bu komutlarla yapılır.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

import typer

from mesveret import clock
from mesveret.config import get_settings

app = typer.Typer(
    help="Meşveret geliştirme araçları (yalnızca geliştirme ortamı).", no_args_is_help=True
)


def _require_dev() -> None:
    if not get_settings().is_dev:
        typer.echo("Bu komut yalnızca geliştirme ortamında (ENV=dev) çalışır.", err=True)
        raise typer.Exit(code=2)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(clock.ISTANBUL).strftime("%Y-%m-%d %H:%M:%S (%A) İstanbul")


@contextmanager
def _ctx():
    from mesveret.context import Ctx
    from mesveret.db.base import create_schema, get_sessionmaker
    from mesveret.main import default_graph, default_ledger

    _require_dev()
    settings = get_settings()
    create_schema()
    graph = default_graph(settings)
    if hasattr(graph, "ensure_constraints"):
        graph.ensure_constraints()
    db = get_sessionmaker()()
    try:
        yield Ctx(db=db, graph=graph, now=clock.now(db), settings=settings,
                  ledger=default_ledger(settings))
    finally:
        db.close()


@app.command()
def now() -> None:
    """Sahte saatin gösterdiği anı ve bir sonraki Karar Saati'ni yazar."""
    from mesveret.services import decision_hour

    with _ctx() as ctx:
        st = decision_hour.status(ctx)
        typer.echo(f"Sahte saat     : {_fmt(ctx.now)}")
        if st["open_session"]:
            typer.echo(f"Açık oturum    : #{st['open_session']['id']}, kapanış "
                       f"{_fmt(st['open_session']['closes_at'])}")
        typer.echo(f"Sonraki Karar Saati: {_fmt(st['next_scheduled_at'])}")
        ctx.db.commit()


@app.command("advance-time")
def advance_time(
    hours: float = typer.Option(0, "--hours", help="İleri alınacak saat"),
    days: float = typer.Option(0, "--days", help="İleri alınacak gün"),
    minutes: float = typer.Option(0, "--minutes", help="İleri alınacak dakika"),
    to: str | None = typer.Option(None, "--to", help="Hedef an (ISO-8601, saat dilimli)"),
) -> None:
    """Sahte saati ileri alır ve aradaki zamanlanmış işleri sırayla, kendi vade anlarında işler."""
    from mesveret.services import scheduler

    with _ctx() as ctx:
        start = ctx.now
        target = (datetime.fromisoformat(to) if to
                  else start + timedelta(hours=hours, days=days, minutes=minutes))
        if target <= start:
            typer.echo("Hedef an şimdiden sonra olmalı.", err=True)
            raise typer.Exit(code=1)
        clock.set_now(ctx.db, target)
        ctx.db.commit()
        done = scheduler.tick(ctx.at(target), target)
        typer.echo(f"{_fmt(start)} → {_fmt(target)}")
        for line in done:
            typer.echo(f"  • {line}")
        if not done:
            typer.echo("  (vadesi gelen iş yok)")


@app.command("run-karar-saati")
def run_karar_saati(
    close: bool = typer.Option(False, "--close", help="Açık oturumu kapat ve sonuçları aç"),
    scripted: bool = typer.Option(
        True, "--scripted-votes/--no-scripted-votes",
        help="Tohumdaki oy planına göre tohum kullanıcılarının oylarını ver",
    ),
) -> None:
    """Hemen bir Karar Saati oturumu açar (ya da --close ile açık olanı kapatır)."""
    from mesveret.services import decision_hour, scheduler

    with _ctx() as ctx:
        if close:
            session = decision_hour.open_session_row(ctx)
            if session is None:
                typer.echo("Açık bir oturum yok.", err=True)
                raise typer.Exit(code=1)
            clock.set_now(ctx.db, max(session.closes_at, ctx.now))
            ctx.db.commit()
            done = scheduler.tick(ctx.at(session.closes_at), session.closes_at)
            typer.echo(f"Oturum #{session.id} kapandı ({_fmt(session.closes_at)}).")
            for line in done:
                typer.echo(f"  • {line}")
            view = decision_hour.session_view(ctx, session.id)
            for item in view["items"]:
                p, r = item["proposal"], item["result"] or {}
                if r.get("kind") == "approval":
                    outcome = f"kazanan metin #{r['winner']}" if r["winner"] else r["note"]
                else:
                    outcome = f"{r.get('yes')}/{r.get('cast')} EVET → " + (
                        "KABUL" if r.get("passed") else "RET")
                typer.echo(f"  #{p['id']} {p['title']}: {outcome}")
            return
        session = decision_hour.open_session(ctx, scripted=False)
        typer.echo(f"Karar Saati #{session.id} açıldı: {_fmt(session.opened_at)} → "
                   f"{_fmt(session.closes_at)}")
        view = decision_hour.session_view(ctx, session.id)
        for item in view["items"]:
            p = item["proposal"]
            typer.echo(f"  #{p['id']} [{p['type']}] {p['title']} — seçmen: {item['eligible_count']}")
        if scripted:
            problems = decision_hour.apply_vote_plan(ctx, session)
            ctx.commit()
            typer.echo("Oy planı uygulandı.")
            for line in problems:
                typer.echo(f"  ! {line}")
        typer.echo("Oylarınızı arayüzden verin; kapatmak için: meşveret-dev run-karar-saati --close")
        scheduler.ensure_state(ctx)
        ctx.db.commit()


@app.command()
def seed(
    reset: bool = typer.Option(False, "--reset", help="Tüm verileri silip baştan kur"),
) -> None:
    """Tohum veriyi ve demo senaryolarını kurar."""
    from mesveret.services import seed as seed_service

    with _ctx() as ctx:
        for line in seed_service.run(ctx, reset=reset):
            typer.echo(line)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
