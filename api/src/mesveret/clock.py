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
    row = _row(session)
    if row.frozen_at is not None:
        return row.frozen_at
    return real_now() + timedelta(microseconds=row.offset_us)


def is_frozen(session: Session) -> bool:
    return _row(session).frozen_at is not None


def set_now(session: Session, target: datetime) -> datetime:
    """Sahte saati ``target`` anına ayarlar (yalnızca ileri). Saat donmuşsa donmuş kalır."""
    if target.tzinfo is None:
        raise ValueError("target saat dilimi içermeli")
    row = _row(session)
    if target < now(session):
        raise ValueError("Sahte saat geri alınamaz.")
    row.offset_us = int((target - real_now()) / timedelta(microseconds=1))
    if row.frozen_at is not None:
        row.frozen_at = target
    session.flush()
    return target


def reset_to(session: Session, target: datetime) -> None:
    """Tohum için: saati herhangi bir ana (geri dahil) kurar."""
    row = _row(session)
    row.offset_us = int((target - real_now()) / timedelta(microseconds=1))
    if row.frozen_at is not None:
        row.frozen_at = target
    session.flush()


def freeze(session: Session, at: datetime | None = None) -> datetime:
    """Demo modu: saat ``at`` anında (verilmezse şimdi) durur."""
    row = _row(session)
    row.frozen_at = at or now(session)
    session.flush()
    return row.frozen_at


def unfreeze(session: Session) -> None:
    """Saat donduğu andan itibaren yeniden akar."""
    row = _row(session)
    if row.frozen_at is not None:
        row.offset_us = int((row.frozen_at - real_now()) / timedelta(microseconds=1))
        row.frozen_at = None
    session.flush()
