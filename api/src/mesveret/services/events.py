"""Alan olayları (Observer deseni).

Bir karar sonuçlandığında olanları (dilekçe gider, takvime etkinlik düşer, kişilere bildirim
gider) karar veren kod bilmez: yalnızca olayı yayımlar. Abone modüller kendilerini
``@subscribe`` ile kaydeder. Yeni bir sonuç (ör. takvim) eklemek, öneri motorunu değiştirmeden
yeni bir abone yazmaktır (Açık/Kapalı ilkesi).

Aboneler yayımlayanla aynı işlemde (transaction) ve eşzamanlı çalışır; bir abonenin hatası
kararın tamamını geri alır. Aboneler birbirinin sonucuna bakmaz, sıraya güvenmez (dilekçe ve
takvim aynı konuda birlikte oluşmaz: muhatap ya kurumdur ya takvim). Defter kaydı bilinçli olarak abone
değildir: hash zincirinin sırası işlem sırasıyla aynı kalmalı, bu yüzden kararı veren kod deftere
doğrudan yazar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mesveret.context import Ctx
from mesveret.db.models import (
    Decision,
    DecisionSession,
    Petition,
    PetitionReply,
    Proposal,
    SessionItem,
    Topic,
)

# --- olaylar ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicAccepted:
    """KONU/ALT_KONU kabul edildi ve konu açıldı."""

    topic: Topic
    proposal: Proposal


@dataclass(frozen=True)
class DecisionMade:
    """Kapanış oylamasında bir metin Karar oldu; konu kapandı."""

    topic: Topic
    proposal: Proposal
    decision: Decision


@dataclass(frozen=True)
class SilentPeriodEnded:
    proposal: Proposal


@dataclass(frozen=True)
class MovedToSlowLane:
    proposal: Proposal
    count: int
    threshold: int


@dataclass(frozen=True)
class SessionClosed:
    session: DecisionSession
    items: list[SessionItem]


@dataclass(frozen=True)
class PetitionSent:
    petition: Petition
    proposer_id: str


@dataclass(frozen=True)
class PetitionReplied:
    petition: Petition
    reply: PetitionReply
    institution: str
    entered_by: str


# --- yayın ----------------------------------------------------------------------------------------

Handler = Callable[[Ctx, Any], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type, list[Handler]] = {}

    def subscribe(self, *event_types: type) -> Callable[[Handler], Handler]:
        def wrap(handler: Handler) -> Handler:
            for t in event_types:
                self._subscribers.setdefault(t, []).append(handler)
            return handler

        return wrap

    def subscribers(self, event_type: type) -> list[Handler]:
        return list(self._subscribers.get(event_type, []))

    def publish(self, ctx: Ctx, event: object) -> None:
        _load_subscribers()
        for handler in self._subscribers.get(type(event), []):
            handler(ctx, event)


BUS = EventBus()
subscribe = BUS.subscribe


def publish(ctx: Ctx, event: object) -> None:
    BUS.publish(ctx, event)


_loaded = False


def _load_subscribers() -> None:
    """Abone modüller kendilerini içe aktarılınca kaydeder; yayından önce yüklü olmaları
    sağlanır (içe aktarma sırasına bağlı kalınmaz)."""
    global _loaded
    if not _loaded:
        _loaded = True
        from mesveret.services import calendar, notifications, petitions  # noqa: F401
