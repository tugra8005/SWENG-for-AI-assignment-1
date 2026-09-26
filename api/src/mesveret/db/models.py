"""PostgreSQL şeması. Aşamalar ilerledikçe tablolar eklenir."""

from sqlalchemy import BigInteger, Integer
from sqlalchemy.orm import Mapped, mapped_column

from mesveret.db.base import Base


class SimClockRow(Base):
    """Sahte saat: tek satır, gerçek saate eklenen ofset (mikrosaniye)."""

    __tablename__ = "sim_clock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    offset_us: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
