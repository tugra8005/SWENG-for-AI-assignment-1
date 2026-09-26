"""Kapsam üyeliği ve oy hakkı (R5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from mesveret.domain.regulation import Regulation

AGE_GROUPS: list[tuple[str, int, int | None]] = [
    ("18-24", 18, 24),
    ("25-34", 25, 34),
    ("35-49", 35, 49),
    ("50+", 50, None),
]

GENERAL_SCOPE_ID = "genel"


class ScopeType(StrEnum):
    GENEL = "GENEL"
    NITELIK = "NITELIK"
    ILGI = "ILGI"


class ScopeSubtype(StrEnum):
    SEHIR = "SEHIR"
    YAS_GRUBU = "YAS_GRUBU"


class MembershipReason(StrEnum):
    KAYIT = "KAYIT"
    ADRES_DEGISIKLIGI = "ADRES_DEGISIKLIGI"
    YAS = "YAS"
    KATILIM = "KATILIM"


@dataclass(frozen=True)
class Membership:
    scope_id: str
    since: datetime
    reason: MembershipReason


def city_scope_id(slug: str) -> str:
    return f"sehir:{slug}"


def age_scope_id(group: str) -> str:
    return f"yas:{group}"


def interest_scope_id(area_id: str) -> str:
    return f"ilgi:{area_id}"


def age_on(birth: date, on: date) -> int:
    years = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day):
        years -= 1
    return years


def age_group(birth: date, on: date) -> str | None:
    age = age_on(birth, on)
    for name, low, high in AGE_GROUPS:
        if age >= low and (high is None or age <= high):
            return name
    return None


def _birthday(birth: date, years: int) -> date:
    try:
        return birth.replace(year=birth.year + years)
    except ValueError:  # 29 Şubat, artık olmayan yıl
        return date(birth.year + years, 3, 1)


def age_group_since(birth: date, group: str) -> date:
    """Kişinin bu yaş grubuna girdiği gün (grubun alt sınırındaki doğum günü)."""
    low = next(low for name, low, _ in AGE_GROUPS if name == group)
    return _birthday(birth, low)


def vote_right_starts(m: Membership, reg: Regulation) -> datetime:
    if m.reason is MembershipReason.KATILIM:
        return m.since + reg.duration("ilgi_bekleme")
    if m.reason is MembershipReason.ADRES_DEGISIKLIGI:
        return m.since + reg.duration("adres_bekleme")
    return m.since


def has_vote_right(m: Membership, now: datetime, reg: Regulation) -> bool:
    return now >= vote_right_starts(m, reg)


def waiting_left(m: Membership, now: datetime, reg: Regulation) -> timedelta:
    return max(timedelta(0), vote_right_starts(m, reg) - now)
