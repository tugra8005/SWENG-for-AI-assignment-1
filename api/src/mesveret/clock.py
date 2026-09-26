"""Sahte saat.

Tüm zaman karşılaştırmaları bu saatle yapılır: ``now = gerçek_utc + ofset``.
Ofset PostgreSQL'de tek satırda durur; API ve geliştirme CLI'ı aynı değeri görür.
Servisler ``now`` değerini parametre olarak alır, saati kendileri okumaz; böylece
zamanlayıcı bir işi kendi vade anında işleyebilir.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from mesveret.db.models import SimClockRow

ISTANBUL = ZoneInfo("Europe/Istanbul")


def real_now() -> datetime:
    return datetime.now(UTC)


def _row(session: Session) -> SimClockRow:
    row = session.get(SimClockRow, 1)
    if row is None:
        row = SimClockRow(id=1, offset_us=0)
        session.add(row)
        session.flush()
    return row


def get_offset(session: Session) -> timedelta:
    return timedelta(microseconds=_row(session).offset_us)


def now(session: Session) -> datetime:
    return real_now() + get_offset(session)


def set_now(session: Session, target: datetime) -> datetime:
    """Sahte saati ``target`` anına ayarlar (yalnızca ileri)."""
    if target.tzinfo is None:
        raise ValueError("target saat dilimi içermeli")
    row = _row(session)
    current = real_now() + timedelta(microseconds=row.offset_us)
    if target < current:
        raise ValueError("Sahte saat geri alınamaz.")
    row.offset_us = int((target - real_now()) / timedelta(microseconds=1))
    session.flush()
    return target


def reset_to(session: Session, target: datetime) -> None:
    """Tohum için: saati herhangi bir ana (geri dahil) kurar."""
    row = _row(session)
    row.offset_us = int((target - real_now()) / timedelta(microseconds=1))
    session.flush()
