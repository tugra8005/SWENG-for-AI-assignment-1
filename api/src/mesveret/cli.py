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
    from mesveret.errors import DomainError
    from mesveret.services import devtools

    with _ctx() as ctx:
        target = (datetime.fromisoformat(to) if to
                  else ctx.now + timedelta(hours=hours, days=days, minutes=minutes))
        try:
            out = devtools.advance(ctx, target)
        except DomainError as exc:
            typer.echo(exc.message, err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"{_fmt(out['from'])} → {_fmt(out['to'])}")
        for line in out["events"] or ["(vadesi gelen iş yok)"]:
            typer.echo(f"  • {line}")


def _print_items(view: dict) -> None:
    for item in view["items"]:
        p, r = item["proposal"], item["result"]
        if r is None:
            typer.echo(f"  #{p['id']} [{p['type']}] {p['title']} — seçmen: {item['eligible_count']}")
        elif r.get("kind") == "approval":
            outcome = f"kazanan metin #{r['winner']}" if r["winner"] else r["note"]
            typer.echo(f"  #{p['id']} {p['title']}: {outcome}")
        else:
            verdict = "KABUL" if r.get("passed") else "RET"
            typer.echo(f"  #{p['id']} {p['title']}: {r.get('yes')}/{r.get('cast')} EVET → {verdict}")


@app.command("run-karar-saati")
def run_karar_saati(
    close: bool = typer.Option(False, "--close", help="Açık oturumu kapat ve oyları aç"),
    scripted: bool = typer.Option(
        True, "--scripted-votes/--no-scripted-votes",
        help="Tohumdaki oy planına göre tohum kullanıcılarının oylarını ver",
    ),
) -> None:
    """Hemen bir Karar Saati oturumu açar (ya da --close ile açık olanı kapatır)."""
    from mesveret.errors import DomainError
    from mesveret.services import devtools

    with _ctx() as ctx:
        try:
            out = (devtools.close_decision_hour(ctx) if close
                   else devtools.open_decision_hour(ctx, scripted=scripted))
        except DomainError as exc:
            typer.echo(exc.message, err=True)
            raise typer.Exit(code=1) from exc
        view = out["session"]
        if close:
            typer.echo(f"Karar Saati #{view['id']} kapandı; oylar açıldı.")
        else:
            typer.echo(f"Karar Saati #{view['id']} açıldı: {_fmt(view['opened_at'])} → "
                       f"{_fmt(view['closes_at'])}")
        _print_items(view)
        for line in out.get("problems", []):
            typer.echo(f"  ! {line}")
        for q in out.get("maturing", []):
            m = q["maturity"]
            typer.echo(f"  ~ #{q['id']} {q['title']} — olgunlaşıyor ({m['label']}, "
                       f"{m['hours']} saat); {_fmt(m['first_session_at'])} oturumunda oylanacak")
        if not close:
            typer.echo("Oyları arayüzden verin; kapatmak için: meşveret-dev run-karar-saati --close")


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
