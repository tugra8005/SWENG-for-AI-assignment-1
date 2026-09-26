"""Ontoloji görünümü.

Kurallar ontolojiye yalnızca ``OntologyView`` protokolü üzerinden bakar. Bellek içi
uygulama testlerde, Neo4j uygulaması (``mesveret.graph.ontology``) serviste kullanılır;
ikisi de aynı sözleşme testlerinden geçer.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from mesveret.domain.scopes import ScopeSubtype, ScopeType


class ResourceKind(StrEnum):
    ALAN = "ALAN"
    KONU = "KONU"
    YONETMELIK_MADDESI = "YONETMELIK_MADDESI"
    ORTAK = "ORTAK"


@dataclass(frozen=True)
class AreaInfo:
    id: str
    name: str
    parent_id: str | None
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeInfo:
    id: str
    type: ScopeType
    name: str
    subtype: ScopeSubtype | None = None
    value: str | None = None


@dataclass(frozen=True)
class ResourceInfo:
    id: str
    kind: ResourceKind
    name: str
    owner_scope_id: str
    divisible: bool = False
    division_type: ScopeSubtype | None = None
    shares: Mapping[str, int] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()


class AreaTree(Protocol):
    def area_ancestors(self, area_id: str) -> list[str]: ...
    def area_descendants_bfs(self, area_id: str) -> list[str]: ...
    def all_area_ids_bfs(self) -> list[str]: ...


class OntologyView(AreaTree, Protocol):
    def area(self, area_id: str) -> AreaInfo | None: ...
    def all_areas(self) -> list[AreaInfo]: ...
    def area_subtree(self, area_id: str) -> set[str]: ...
    def scope(self, scope_id: str) -> ScopeInfo | None: ...
    def city_scopes(self) -> list[ScopeInfo]: ...
    def is_strict_subset(self, scope_id: str, of_scope_id: str) -> bool: ...
    def resource(self, resource_id: str) -> ResourceInfo | None: ...
    def all_resources(self) -> list[ResourceInfo]: ...
    def topic_area(self, topic_id: str) -> str | None: ...


class InMemoryOntology:
    def __init__(
        self,
        areas: Iterable[AreaInfo],
        scopes: Iterable[ScopeInfo],
        subset_of: Mapping[str, set[str]],
        resources: Iterable[ResourceInfo],
        topic_areas: Mapping[str, str] | None = None,
    ):
        self._areas = {a.id: a for a in areas}
        self._children: dict[str | None, list[str]] = {}
        for a in sorted(self._areas.values(), key=lambda a: a.id):
            self._children.setdefault(a.parent_id, []).append(a.id)
        self._scopes = {s.id: s for s in scopes}
        self._subset_of = {k: set(v) for k, v in subset_of.items()}
        self._resources = {r.id: r for r in resources}
        self._topic_areas = dict(topic_areas or {})

    # --- alanlar ---
    def area(self, area_id: str) -> AreaInfo | None:
        return self._areas.get(area_id)

    def all_areas(self) -> list[AreaInfo]:
        return [self._areas[i] for i in self.all_area_ids_bfs()]

    def area_ancestors(self, area_id: str) -> list[str]:
        chain: list[str] = []
        current: str | None = area_id
        while current is not None and current in self._areas and current not in chain:
            chain.append(current)
            current = self._areas[current].parent_id
        return chain

    def _bfs(self, roots: list[str]) -> list[str]:
        order: list[str] = []
        queue = deque(roots)
        while queue:
            node = queue.popleft()
            order.append(node)
            queue.extend(self._children.get(node, []))
        return order

    def area_descendants_bfs(self, area_id: str) -> list[str]:
        return self._bfs([area_id]) if area_id in self._areas else []

    def all_area_ids_bfs(self) -> list[str]:
        return self._bfs(list(self._children.get(None, [])))

    def area_subtree(self, area_id: str) -> set[str]:
        return set(self.area_descendants_bfs(area_id))

    # --- kapsamlar ---
    def scope(self, scope_id: str) -> ScopeInfo | None:
        return self._scopes.get(scope_id)

    def city_scopes(self) -> list[ScopeInfo]:
        return [s for s in self._scopes.values() if s.subtype is ScopeSubtype.SEHIR]

    def is_strict_subset(self, scope_id: str, of_scope_id: str) -> bool:
        seen: set[str] = set()
        frontier = [scope_id]
        while frontier:
            current = frontier.pop()
            for parent in self._subset_of.get(current, set()):
                if parent == of_scope_id:
                    return True
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        return False

    # --- kaynaklar ---
    def resource(self, resource_id: str) -> ResourceInfo | None:
        return self._resources.get(resource_id)

    def all_resources(self) -> list[ResourceInfo]:
        return list(self._resources.values())

    def topic_area(self, topic_id: str) -> str | None:
        return self._topic_areas.get(topic_id)
