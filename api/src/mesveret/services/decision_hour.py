"""Karar Saati. (e) aşamasında doldurulur."""

from __future__ import annotations

from datetime import datetime

from mesveret.context import Ctx


def due_events(ctx: Ctx, until: datetime, last: datetime | None) -> list:
    return []
