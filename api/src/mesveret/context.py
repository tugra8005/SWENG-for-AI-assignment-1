"""İstek bağlamı: veritabanı oturumu, graf, sahte saat anı, defter istemcisi.

Servisler zamanı ``ctx.now`` üzerinden alır; zamanlayıcı bir işi kendi vade anında
işlerken ``ctx.at(t)`` ile aynı bağlamı başka bir anla kullanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from mesveret.config import Settings
from mesveret.domain.ontology import ScopeInfo
from mesveret.domain.regulation import Regulation
from mesveret.graph.store import GraphStore

if TYPE_CHECKING:
    from mesveret.services.ledger import LedgerClient


@dataclass
class Ctx:
    db: Session
    graph: GraphStore
    now: datetime
    settings: Settings
    ledger: LedgerClient
    _reg: Regulation | None = field(default=None, repr=False)
    _cities: list[ScopeInfo] | None = field(default=None, repr=False)

    @property
    def reg(self) -> Regulation:
        if self._reg is None:
            self._reg = Regulation(self.graph.articles(), self.graph.unchangeable_articles())
        return self._reg

    @property
    def cities(self) -> list[ScopeInfo]:
        """Şehir kapsamları (muhatap kataloğu için; istek başına bir kez okunur)."""
        if self._cities is None:
            self._cities = self.graph.city_scopes()
        return self._cities

    def invalidate_regulation(self) -> None:
        self._reg = None

    def at(self, when: datetime) -> Ctx:
        return replace(self, now=when, _reg=None, _cities=None)

    def commit(self) -> None:
        """PostgreSQL işlemini tamamlar, ardından defter outbox'ını göndermeyi dener."""
        from mesveret.services import ledger

        self.db.commit()
        ledger.flush(self)
