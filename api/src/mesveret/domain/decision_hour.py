"""Karar Saati takvimi (``karar_saati`` maddesinden)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from mesveret.domain.regulation import DecisionHourSpec


def next_occurrence(after: datetime, spec: DecisionHourSpec) -> datetime:
    """``after`` anından kesinlikle sonraki ilk oturum anı (UTC ile aynı saat dilimli)."""
    tz = ZoneInfo(spec.tz)
    local = after.astimezone(tz)
    days_ahead = (spec.weekday - local.weekday()) % 7
    candidate = datetime.combine(
        local.date() + timedelta(days=days_ahead), time(spec.hour, spec.minute), tzinfo=tz
    )
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate.astimezone(after.tzinfo)
