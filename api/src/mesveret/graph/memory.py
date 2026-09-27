"""Bellek içi graf deposu (testler için). Davranışı ``Neo4jGraph`` ile aynıdır."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import datetime
from typing import Any

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
        self._delegations: dict[tuple[str, str | None], tuple[str, datetime]] = {}
        self._interactions: dict[tuple[str, str], float] = {}
        self._articles: dict[str, dict[str, Any]] = {}
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
    def delegations(self) -> dict[tuple[str, str | None], str]:
        return {k: t for k, (t, _) in self._delegations.items()}

    def outgoing_delegations(self, user_id: str) -> list[tuple[str | None, str, datetime]]:
        rows = [(a, t, s) for (u, a), (t, s) in self._delegations.items() if u == user_id]
        return sorted(rows, key=lambda r: (r[0] is not None, r[0] or ""))

    def incoming_delegations(self, user_id: str) -> dict[str | None, int]:
        counts: dict[str | None, int] = {}
        for (_, a), (t, _) in self._delegations.items():
            if t == user_id:
                counts[a] = counts.get(a, 0) + 1
        return counts

    def set_delegation(self, user_id: str, target_id: str, area_id: str | None, since: datetime) -> None:
        self._delegations[(user_id, area_id)] = (target_id, since)

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
