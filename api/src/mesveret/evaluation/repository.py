"""Senaryo depoları (Repository deseni).

Değerlendirme senaryoların nereden geldiğini bilmez: dosyadaki sabit sınama kümesi, tohumdan
üretilen eğitim kümesi, canlı yığındaki gerçek Karar Saati anlık görüntüsü ya da testlerdeki
bellek içi liste aynı arayüzle okunur.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from mesveret.evaluation.scenarios import Scenario, generate, split_of


class ScenarioRepository(ABC):
    @abstractmethod
    def load(self, split: str) -> list[Scenario]:
        """``split``: "egitim" ya da "sinama"."""


class InMemoryScenarioRepository(ScenarioRepository):
    """Birim testleri için sahte depo."""

    def __init__(self, train: list[Scenario], test: list[Scenario]) -> None:
        self._sets = {"egitim": list(train), "sinama": list(test)}

    def load(self, split: str) -> list[Scenario]:
        return list(self._sets[split])


class GeneratedScenarioRepository(ScenarioRepository):
    """Tohumdan üretilen senaryolar; adın hash'iyle eğitim/sınama ayrımı."""

    def __init__(self, count: int, seed: int, test_share: float = 0.3) -> None:
        self.count, self.seed, self.test_share = count, seed, test_share
        self._all: list[Scenario] | None = None

    def load(self, split: str) -> list[Scenario]:
        if self._all is None:
            self._all = generate(self.count, self.seed)
        return [s for s in self._all if split_of(s.name, self.test_share) == split]


class JsonScenarioRepository(ScenarioRepository):
    """Dosyaya yazılmış sabit küme: ``{"egitim": [...], "sinama": [...]}``. Sınama kümesi bir kez
    yazılır ve değiştirilmez; her model aynı senaryolarda yarışır."""

    def __init__(self, path: str | Path, fallback: ScenarioRepository | None = None) -> None:
        self.path, self.fallback = Path(path), fallback

    def load(self, split: str) -> list[Scenario]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if split not in data and self.fallback is not None:
            return self.fallback.load(split)
        return [Scenario.from_json(d) for d in data[split]]

    @staticmethod
    def freeze(path: str | Path, scenarios: list[Scenario], split: str = "sinama") -> None:
        Path(path).write_text(json.dumps({split: [s.to_json() for s in scenarios]},
                                         ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


class LiveScenarioRepository(ScenarioRepository):
    """Canlı yığındaki ilk Karar Saati'nin Genel seçmen anlık görüntüsü; etiket tohumdaki
    baskıncılardır. Yalnızca sınama için (eğitim kümesi yok)."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    def load(self, split: str) -> list[Scenario]:
        if split != "sinama":
            return []
        from sqlalchemy import select

        from mesveret.db.models import DecisionSession, User
        from mesveret.services import ontology
        from mesveret.services.seed import RAIDERS

        session = self.ctx.db.execute(
            select(DecisionSession).order_by(DecisionSession.id)).scalars().first()
        if session is None:
            return []
        c = self.ctx.at(session.opened_at)
        members = ontology.eligible_voters(c, "genel")
        nick = {u.id: u.nickname for u in self.ctx.db.execute(select(User)).scalars()}
        return [Scenario(
            name=f"karar-saati-{session.id}", at=session.opened_at,
            joined={nick.get(u, u): m.since for u, m in members.items()},
            interactions={(nick.get(a, a), nick.get(b, b)): w for (a, b), w in
                          self.ctx.graph.interactions_among(members).items()},
            raiders=frozenset(n for n in (nick.get(u) for u in members) if n in RAIDERS),
        )]
