"""Mahzen kuralları: ifşa eşiği, yükselme, kapasite, ömür ve referans engeli."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from mesveret.domain.regulation import Ratio

_THREAD_LINK = re.compile(r"mahzen/(\d+)", re.IGNORECASE)
_POST_REF = re.compile(r">>(\d+)")


@dataclass(frozen=True)
class ThreadState:
    id: int
    bumped_at: datetime
    frozen: bool


def reveal_passes(yes_votes: int, electorate: int, ratio: Ratio) -> bool:
    """EVET sayısı seçmen listesinin eşik payını aştığı an ifşa gerçekleşir."""
    return ratio.passes(yes_votes, electorate)


def should_bump(replies_before: int, limit: int) -> bool:
    """Üst sınıra ulaşmış başlık yeni yanıtla yükselmez."""
    return replies_before < limit


def threads_to_prune(threads: Iterable[ThreadState], capacity: int) -> list[int]:
    """Kapasiteyi aşan yaşayan başlıklar, en yeni yükselenden eskiye sıralı listenin sonu."""
    living = sorted((t for t in threads if not t.frozen), key=lambda t: t.bumped_at, reverse=True)
    return [t.id for t in living[capacity:]]


def lifetime_remaining(rank: int, capacity: int) -> float:
    """0 = silinmek üzere, 1 = en üstte. ``rank`` 0'dan başlar."""
    if capacity <= 0:
        return 0.0
    return max(0.0, min(1.0, (capacity - rank) / capacity))


def cellar_thread_refs(text: str) -> set[int]:
    return {int(m) for m in _THREAD_LINK.findall(text)}


def post_refs(text: str) -> set[int]:
    return {int(m) for m in _POST_REF.findall(text)}
