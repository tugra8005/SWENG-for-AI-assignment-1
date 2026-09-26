"""Geliştirme CLI'ı: ``meşveret-dev`` (ASCII takma adı ``mesveret-dev``).

Yalnızca ``ENV=dev`` iken çalışır. Demo bu komutlarla yapılır.
"""

from datetime import datetime, timedelta

import typer

from mesveret import clock
from mesveret.config import get_settings
from mesveret.db.base import create_schema, get_sessionmaker

app = typer.Typer(help="Meşveret geliştirme araçları (yalnızca geliştirme ortamı).", no_args_is_help=True)


def _require_dev() -> None:
    if not get_settings().is_dev:
        typer.echo("Bu komut yalnızca geliştirme ortamında (ENV=dev) çalışır.", err=True)
        raise typer.Exit(code=2)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(clock.ISTANBUL).strftime("%Y-%m-%d %H:%M:%S %Z")


@app.command()
def now() -> None:
    """Sahte saatin gösterdiği anı yazar."""
    _require_dev()
    create_schema()
    with get_sessionmaker()() as s:
        typer.echo(_fmt(clock.now(s)))
        s.commit()


@app.command("advance-time")
def advance_time(
    hours: float = typer.Option(0, "--hours", help="İleri alınacak saat"),
    days: float = typer.Option(0, "--days", help="İleri alınacak gün"),
    to: str | None = typer.Option(None, "--to", help="Hedef an (ISO-8601, saat dilimli)"),
) -> None:
    """Sahte saati ileri alır ve aradaki zamanlanmış işleri sırayla işler."""
    _require_dev()
    create_schema()
    with get_sessionmaker()() as s:
        start = clock.now(s)
        if to is not None:
            target = datetime.fromisoformat(to)
        else:
            target = start + timedelta(hours=hours, days=days)
        if target <= start:
            typer.echo("Hedef an şimdiden sonra olmalı.", err=True)
            raise typer.Exit(code=1)
        clock.set_now(s, target)
        s.commit()
        typer.echo(f"{_fmt(start)} → {_fmt(target)}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
