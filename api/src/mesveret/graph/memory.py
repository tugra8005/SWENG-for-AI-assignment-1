"""Bellek içi graf deposu (testler için). Davranışı ``Neo4jGraph`` ile aynıdır."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from mesveret.domain.delegation import DelegationEdge
from mesveret.domain.ontology import AreaInfo, InMemoryOntology, ResourceInfo, ScopeInfo
from mesveret.domain.scopes import Membership


class InMemoryGraph(InMemoryOntology):
    def __init__(self) -> None:
        super().__init__([], [], {}, [])
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        self._areas = {}
        self._rebuild_children()
        self._scopes = {}
        self._subset_of = {}
        self._resources = {}
        self._topic_areas = {}
        self._topic_parents: dict[str, str] = {}
        self._users: dict[str, dict] = {}
        self._members: dict[str, dict[str, Membership]] = {}
        self._delegations: dict[tuple[str, str | None], DelegationEdge] = {}
        self._interactions: dict[tuple[str, str], float] = {}
        self._articles: dict[str, dict[str, Any]] = {}
        self._unchangeable: set[str] = set()
        self._proposals: dict[int, dict] = {}
        self._decisions: dict[int, str] = {}
        self._discourse: dict[int, dict[str, datetime]] = {}

    # --- ontoloji ---
    def upsert_area(self, area: AreaInfo) -> None:
        self._areas[area.id] = area
        self._rebuild_children()

    def upsert_scope(self, scope: ScopeInfo, subset_of: set[str]) -> None:
        self._scopes[scope.id] = scope
        self._subset_of[scope.id] = set(subset_of)

    def upsert_resource(
        self, r: ResourceInfo, topic_area_id: str | None = None, parent_topic_id: str | None = None
    ) -> None:
        self._resources[r.id] = r
        if topic_area_id is not None:
            self._topic_areas[r.id] = topic_area_id
        if parent_topic_id is not None:
            self._topic_parents[r.id] = parent_topic_id

    # --- kullanıcılar ve üyelik ---
    def upsert_user(self, user_id: str, nickname: str, role: str, created_at: datetime) -> None:
        self._users[user_id] = {"nickname": nickname, "role": role, "created_at": created_at}

    def set_membership(self, user_id: str, m: Membership) -> None:
        self._members.setdefault(m.scope_id, {})[user_id] = m

    def remove_membership(self, user_id: str, scope_id: str) -> None:
        self._members.get(scope_id, {}).pop(user_id, None)

    def memberships(self, user_id: str) -> list[Membership]:
        return sorted(
            (ms[user_id] for ms in self._members.values() if user_id in ms),
            key=lambda m: m.scope_id,
        )

    def scope_members(self, scope_id: str) -> dict[str, Membership]:
        return dict(self._members.get(scope_id, {}))

    # --- havale ---
    def delegation_edges(self, active_at: datetime | None = None) -> list[DelegationEdge]:
        return [e for e in self._delegations.values() if active_at is None or e.active_at(active_at)]

    def delegations(self, active_at: datetime | None = None) -> dict[tuple[str, str | None], str]:
        return {(e.user_id, e.area_id): e.target_id for e in self.delegation_edges(active_at)}

    def outgoing_delegations(
        self, user_id: str, active_at: datetime | None = None
    ) -> list[DelegationEdge]:
        rows = [e for e in self.delegation_edges(active_at) if e.user_id == user_id]
        return sorted(rows, key=lambda e: (e.area_id is not None, e.area_id or ""))

    def incoming_delegations(
        self, user_id: str, active_at: datetime | None = None
    ) -> dict[str | None, int]:
        counts: dict[str | None, int] = {}
        for e in self.delegation_edges(active_at):
            if e.target_id == user_id:
                counts[e.area_id] = counts.get(e.area_id, 0) + 1
        return counts

    def set_delegation(
        self, user_id: str, target_id: str, area_id: str | None, since: datetime,
        expires_at: datetime | None = None,
    ) -> None:
        self._delegations[(user_id, area_id)] = DelegationEdge(
            user_id, area_id, target_id, since, expires_at)

    def renew_delegation(self, user_id: str, area_id: str | None, expires_at: datetime) -> bool:
        e = self._delegations.get((user_id, area_id))
        if e is None:
            return False
        self._delegations[(user_id, area_id)] = DelegationEdge(
            user_id, area_id, e.target_id, e.since, expires_at)
        return True

    def remove_delegation(self, user_id: str, area_id: str | None) -> bool:
        return self._delegations.pop((user_id, area_id), None) is not None

    # --- etkileşim ---
    def add_interaction(self, a: str, b: str, weight: float) -> None:
        if a == b:
            return
        self._interactions[(a, b)] = self._interactions.get((a, b), 0.0) + weight

    def interactions_among(self, users: Iterable[str]) -> dict[tuple[str, str], float]:
        us = set(users)
        return {k: w for k, w in self._interactions.items() if k[0] in us and k[1] in us}

    # --- yönetmelik ---
    def articles(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self._articles.items()}

    def set_article(self, key: str, value: dict[str, Any]) -> None:
        self._articles[key] = dict(value)

    def delete_article(self, key: str) -> None:
        self._articles.pop(key, None)

    def set_unchangeable(self, key: str) -> None:
        self._unchangeable.add(key)

    def clear_unchangeable(self, key: str) -> None:
        self._unchangeable.discard(key)

    def unchangeable_articles(self) -> frozenset[str]:
        return frozenset(self._unchangeable)

    # --- öneri, karar, diskur ---
    def record_proposal(
        self, proposal_id: int, type_: str, scope_id: str, resource_ids: list[str], status: str
    ) -> None:
        self._proposals[proposal_id] = {
            "type": type_, "scope": scope_id, "resources": list(resource_ids), "status": status,
        }

    def set_proposal_status(self, proposal_id: int, status: str) -> None:
        if proposal_id in self._proposals:
            self._proposals[proposal_id]["status"] = status

    def record_decision(self, decision_id: int, topic_resource_id: str) -> None:
        self._decisions[decision_id] = topic_resource_id

    def add_discourse_author(self, thread_id: int, user_id: str, first_at: datetime) -> None:
        self._discourse.setdefault(thread_id, {}).setdefault(user_id, first_at)

    def discourse_authors(self, thread_id: int) -> dict[str, datetime]:
        return dict(self._discourse.get(thread_id, {}))

    def remove_discourse(self, thread_id: int) -> None:
        self._discourse.pop(thread_id, None)
