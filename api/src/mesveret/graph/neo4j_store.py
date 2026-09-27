"""Neo4j graf deposu.

Düğüm ve ilişki adları DESIGN.md §4'teki ontolojiyle aynıdır. Neo4j özellikleri harita
(map) tutamadığı için şehir payları ve madde değerleri JSON metni olarak saklanır; genel
havalede ``alan_id`` özelliği hiç yazılmaz (Neo4j null özellik saklamaz).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from neo4j import Driver, Query

from mesveret.domain.ontology import AreaInfo, ResourceInfo, ResourceKind, ScopeInfo
from mesveret.domain.scopes import Membership, MembershipReason, ScopeSubtype, ScopeType

CONSTRAINTS = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (n:User) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT alan_id IF NOT EXISTS FOR (n:Alan) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT kapsam_id IF NOT EXISTS FOR (n:Kapsam) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT kaynak_id IF NOT EXISTS FOR (n:Kaynak) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT madde_anahtar IF NOT EXISTS FOR (n:YonetmelikMaddesi) REQUIRE n.anahtar IS UNIQUE",
    "CREATE CONSTRAINT oneri_id IF NOT EXISTS FOR (n:Oneri) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT karar_id IF NOT EXISTS FOR (n:Karar) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT diskur_id IF NOT EXISTS FOR (n:Diskur) REQUIRE n.id IS UNIQUE",
]

ARTICLE_PREFIX = "madde:"


def _dt(value: Any) -> datetime:
    """neo4j.time.DateTime → UTC datetime."""
    native = value.to_native() if hasattr(value, "to_native") else value
    return native.astimezone(UTC)


class Neo4jGraph:
    def __init__(self, driver: Driver, database: str = "neo4j"):
        self._driver = driver
        self._db = database

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(Query(query), params, database_=self._db)
        return [r.data() for r in records]

    def ensure_constraints(self) -> None:
        for q in CONSTRAINTS:
            self._run(q)

    def reset(self) -> None:
        self._run("MATCH (n) DETACH DELETE n")

    # --- alanlar ---
    @staticmethod
    def _area(row: dict) -> AreaInfo:
        return AreaInfo(row["id"], row["ad"], row.get("ust"), tuple(row.get("kelimeler") or ()))

    _AREA_RETURN = "a.id AS id, a.ad AS ad, a.anahtar_kelimeler AS kelimeler, p.id AS ust"

    def area(self, area_id: str) -> AreaInfo | None:
        rows = self._run(
            "MATCH (a:Alan {id: $id}) OPTIONAL MATCH (a)-[:ALT_ALANI]->(p:Alan) "
            f"RETURN {self._AREA_RETURN}",
            id=area_id,
        )
        return self._area(rows[0]) if rows else None

    def all_areas(self) -> list[AreaInfo]:
        rows = self._run(
            "MATCH (a:Alan) OPTIONAL MATCH (a)-[:ALT_ALANI]->(p:Alan) "
            "OPTIONAL MATCH path = (a)-[:ALT_ALANI*0..]->(r:Alan) "
            "WHERE NOT EXISTS { MATCH (r)-[:ALT_ALANI]->() } "
            f"RETURN {self._AREA_RETURN}, length(path) AS d ORDER BY d, id"
        )
        return [self._area(r) for r in rows]

    def area_ancestors(self, area_id: str) -> list[str]:
        rows = self._run(
            "MATCH path = (a:Alan {id: $id})-[:ALT_ALANI*0..]->(p:Alan) "
            "RETURN p.id AS id ORDER BY length(path)",
            id=area_id,
        )
        return [r["id"] for r in rows]

    def area_descendants_bfs(self, area_id: str) -> list[str]:
        rows = self._run(
            "MATCH path = (c:Alan)-[:ALT_ALANI*0..]->(a:Alan {id: $id}) "
            "RETURN c.id AS id, length(path) AS d ORDER BY d, id",
            id=area_id,
        )
        return [r["id"] for r in rows]

    def all_area_ids_bfs(self) -> list[str]:
        return [a.id for a in self.all_areas()]

    def area_subtree(self, area_id: str) -> set[str]:
        return set(self.area_descendants_bfs(area_id))

    def upsert_area(self, area: AreaInfo) -> None:
        self._run(
            "MERGE (a:Alan {id: $id}) SET a.ad = $ad, a.anahtar_kelimeler = $kw "
            "WITH a OPTIONAL MATCH (a)-[old:ALT_ALANI]->() DELETE old "
            "WITH a OPTIONAL MATCH (p:Alan {id: $ust}) "
            "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (a)-[:ALT_ALANI]->(p))",
            id=area.id, ad=area.name, kw=list(area.keywords), ust=area.parent_id,
        )

    # --- kapsamlar ---
    @staticmethod
    def _scope(row: dict) -> ScopeInfo:
        return ScopeInfo(
            row["id"], ScopeType(row["tur"]), row["ad"],
            ScopeSubtype(row["alt_tur"]) if row.get("alt_tur") else None, row.get("deger"),
        )

    _SCOPE_RETURN = "k.id AS id, k.tur AS tur, k.ad AS ad, k.alt_tur AS alt_tur, k.deger AS deger"

    def scope(self, scope_id: str) -> ScopeInfo | None:
        rows = self._run(f"MATCH (k:Kapsam {{id: $id}}) RETURN {self._SCOPE_RETURN}", id=scope_id)
        return self._scope(rows[0]) if rows else None

    def city_scopes(self) -> list[ScopeInfo]:
        rows = self._run(
            f"MATCH (k:Kapsam {{alt_tur: 'SEHIR'}}) RETURN {self._SCOPE_RETURN} ORDER BY id"
        )
        return [self._scope(r) for r in rows]

    def is_strict_subset(self, scope_id: str, of_scope_id: str) -> bool:
        if scope_id == of_scope_id:
            return False
        rows = self._run(
            "MATCH (s:Kapsam {id: $s}), (o:Kapsam {id: $o}) "
            "RETURN EXISTS { MATCH (s)-[:ALT_KUMESI*1..]->(o) } AS sub",
            s=scope_id, o=of_scope_id,
        )
        return bool(rows and rows[0]["sub"])

    def upsert_scope(self, scope: ScopeInfo, subset_of: set[str]) -> None:
        self._run(
            "MERGE (k:Kapsam {id: $id}) "
            "SET k.tur = $tur, k.ad = $ad, k.alt_tur = $alt_tur, k.deger = $deger "
            "WITH k OPTIONAL MATCH (k)-[old:ALT_KUMESI]->() DELETE old "
            "WITH DISTINCT k UNWIND $ust AS ust MATCH (p:Kapsam {id: ust}) MERGE (k)-[:ALT_KUMESI]->(p)",
            id=scope.id, tur=str(scope.type), ad=scope.name,
            alt_tur=str(scope.subtype) if scope.subtype else None, deger=scope.value,
            ust=sorted(subset_of),
        )

    # --- kaynaklar ---
    @staticmethod
    def _resource(row: dict) -> ResourceInfo:
        return ResourceInfo(
            row["id"], ResourceKind(row["tur"]), row["ad"], row["sahip"],
            bool(row.get("bolunebilir")),
            ScopeSubtype(row["bolunme"]) if row.get("bolunme") else None,
            json.loads(row.get("paylar") or "{}"),
            tuple(row.get("es_adlar") or ()),
        )

    _RESOURCE_RETURN = (
        "r.id AS id, r.tur AS tur, r.ad AS ad, s.id AS sahip, r.bolunebilir AS bolunebilir, "
        "r.bolunme_turu AS bolunme, r.paylar_json AS paylar, r.es_adlar AS es_adlar"
    )

    def resource(self, resource_id: str) -> ResourceInfo | None:
        rows = self._run(
            f"MATCH (r:Kaynak {{id: $id}})-[:SAHIBI]->(s:Kapsam) RETURN {self._RESOURCE_RETURN}",
            id=resource_id,
        )
        return self._resource(rows[0]) if rows else None

    def all_resources(self) -> list[ResourceInfo]:
        rows = self._run(
            f"MATCH (r:Kaynak)-[:SAHIBI]->(s:Kapsam) RETURN {self._RESOURCE_RETURN} ORDER BY id"
        )
        return [self._resource(r) for r in rows]

    def topic_area(self, topic_id: str) -> str | None:
        rows = self._run(
            "MATCH (:Konu {id: $id})-[:ALANINDA]->(a:Alan) RETURN a.id AS id", id=topic_id
        )
        return rows[0]["id"] if rows else None

    def upsert_resource(
        self, r: ResourceInfo, topic_area_id: str | None = None, parent_topic_id: str | None = None
    ) -> None:
        params: dict[str, Any] = {
            "id": r.id, "tur": str(r.kind), "ad": r.name, "sahip": r.owner_scope_id,
            "bolunebilir": r.divisible,
            "bolunme": str(r.division_type) if r.division_type else None,
            "paylar": json.dumps(dict(r.shares), ensure_ascii=False),
            "es_adlar": list(r.aliases),
        }
        if r.kind is ResourceKind.YONETMELIK_MADDESI:
            # Madde düğümü anahtarıyla tekildir; önce set_article çağrılmış olabilir.
            head = ("MERGE (r:YonetmelikMaddesi {anahtar: $anahtar}) SET r:Kaynak, r.id = $id ")
            params["anahtar"] = r.id.removeprefix(ARTICLE_PREFIX)
        else:
            head = "MERGE (r:Kaynak {id: $id}) "
        self._run(
            head
            + "SET r.tur = $tur, r.ad = $ad, r.bolunebilir = $bolunebilir, "
            "r.bolunme_turu = $bolunme, r.paylar_json = $paylar, r.es_adlar = $es_adlar "
            "WITH r OPTIONAL MATCH (r)-[old:SAHIBI]->() DELETE old "
            "WITH DISTINCT r MATCH (s:Kapsam {id: $sahip}) MERGE (r)-[:SAHIBI]->(s)",
            **params,
        )
        if r.kind is ResourceKind.KONU:
            self._run(
                "MATCH (r:Kaynak {id: $id}) SET r:Konu "
                "WITH r OPTIONAL MATCH (r)-[old:ALANINDA|ALT_KONUSU]->() DELETE old "
                "WITH DISTINCT r OPTIONAL MATCH (a:Alan {id: $alan}) "
                "FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END | MERGE (r)-[:ALANINDA]->(a)) "
                "WITH r OPTIONAL MATCH (p:Konu {id: $ust}) "
                "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (r)-[:ALT_KONUSU]->(p))",
                id=r.id, alan=topic_area_id, ust=parent_topic_id,
            )

    # --- kullanıcılar ve üyelik ---
    def upsert_user(self, user_id: str, nickname: str, role: str, created_at: datetime) -> None:
        self._run(
            "MERGE (u:User {id: $id}) SET u.takma_ad = $nick, u.rol = $rol, u.created_at = $t",
            id=user_id, nick=nickname, rol=role, t=created_at,
        )

    def set_membership(self, user_id: str, m: Membership) -> None:
        self._run(
            "MATCH (u:User {id: $u}), (k:Kapsam {id: $k}) "
            "MERGE (u)-[r:UYE]->(k) SET r.since = $since, r.neden = $neden",
            u=user_id, k=m.scope_id, since=m.since, neden=str(m.reason),
        )

    def remove_membership(self, user_id: str, scope_id: str) -> None:
        self._run(
            "MATCH (:User {id: $u})-[r:UYE]->(:Kapsam {id: $k}) DELETE r", u=user_id, k=scope_id
        )

    def memberships(self, user_id: str) -> list[Membership]:
        rows = self._run(
            "MATCH (:User {id: $u})-[r:UYE]->(k:Kapsam) "
            "RETURN k.id AS k, r.since AS since, r.neden AS neden ORDER BY k",
            u=user_id,
        )
        return [Membership(r["k"], _dt(r["since"]), MembershipReason(r["neden"])) for r in rows]

    def scope_members(self, scope_id: str) -> dict[str, Membership]:
        rows = self._run(
            "MATCH (u:User)-[r:UYE]->(:Kapsam {id: $k}) "
            "RETURN u.id AS u, r.since AS since, r.neden AS neden",
            k=scope_id,
        )
        return {r["u"]: Membership(scope_id, _dt(r["since"]), MembershipReason(r["neden"])) for r in rows}

    # --- havale ---
    def delegations(self) -> dict[tuple[str, str | None], str]:
        rows = self._run(
            "MATCH (u:User)-[r:HAVALE]->(t:User) RETURN u.id AS u, r.alan_id AS a, t.id AS t"
        )
        return {(r["u"], r["a"]): r["t"] for r in rows}

    def outgoing_delegations(self, user_id: str) -> list[tuple[str | None, str, datetime]]:
        rows = self._run(
            "MATCH (:User {id: $u})-[r:HAVALE]->(t:User) "
            "RETURN r.alan_id AS a, t.id AS t, r.since AS since",
            u=user_id,
        )
        out = [(r["a"], r["t"], _dt(r["since"])) for r in rows]
        return sorted(out, key=lambda x: (x[0] is not None, x[0] or ""))

    def incoming_delegations(self, user_id: str) -> dict[str | None, int]:
        rows = self._run(
            "MATCH (:User)-[r:HAVALE]->(:User {id: $u}) RETURN r.alan_id AS a, count(*) AS n",
            u=user_id,
        )
        return {r["a"]: r["n"] for r in rows}

    def set_delegation(self, user_id: str, target_id: str, area_id: str | None, since: datetime) -> None:
        self.remove_delegation(user_id, area_id)
        self._run(
            "MATCH (u:User {id: $u}), (t:User {id: $t}) "
            "CREATE (u)-[r:HAVALE {since: $since}]->(t) SET r.alan_id = $a",
            u=user_id, t=target_id, a=area_id, since=since,
        )

    def remove_delegation(self, user_id: str, area_id: str | None) -> bool:
        rows = self._run(
            "MATCH (:User {id: $u})-[r:HAVALE]->() "
            "WHERE coalesce(r.alan_id, '') = coalesce($a, '') "
            "DELETE r RETURN count(*) AS n",
            u=user_id, a=area_id,
        )
        return bool(rows and rows[0]["n"])

    # --- etkileşim ---
    def add_interaction(self, a: str, b: str, weight: float) -> None:
        if a == b:
            return
        self._run(
            "MATCH (x:User {id: $a}), (y:User {id: $b}) MERGE (x)-[r:ETKILESIM]->(y) "
            "ON CREATE SET r.agirlik = $w ON MATCH SET r.agirlik = r.agirlik + $w",
            a=a, b=b, w=float(weight),
        )

    def interactions_among(self, users: Iterable[str]) -> dict[tuple[str, str], float]:
        rows = self._run(
            "MATCH (x:User)-[r:ETKILESIM]->(y:User) WHERE x.id IN $us AND y.id IN $us "
            "RETURN x.id AS a, y.id AS b, r.agirlik AS w",
            us=sorted(set(users)),
        )
        return {(r["a"], r["b"]): r["w"] for r in rows}

    # --- yönetmelik ---
    def articles(self) -> dict[str, dict[str, Any]]:
        rows = self._run(
            "MATCH (m:YonetmelikMaddesi) WHERE m.deger_json IS NOT NULL "
            "RETURN m.anahtar AS k, m.deger_json AS v"
        )
        return {r["k"]: json.loads(r["v"]) for r in rows}

    def set_article(self, key: str, value: dict[str, Any]) -> None:
        self._run(
            "MERGE (m:YonetmelikMaddesi {anahtar: $k}) SET m.deger_json = $v",
            k=key, v=json.dumps(value, ensure_ascii=False, sort_keys=True),
        )

    # --- öneri, karar, diskur ---
    def record_proposal(
        self, proposal_id: int, type_: str, scope_id: str, resource_ids: list[str], status: str
    ) -> None:
        self._run(
            "MERGE (o:Oneri {id: $id}) SET o.tur = $tur, o.durum = $durum "
            "WITH o OPTIONAL MATCH (o)-[old:SECMEN|ETKILER]->() DELETE old "
            "WITH DISTINCT o MATCH (k:Kapsam {id: $k}) MERGE (o)-[:SECMEN]->(k) "
            "WITH o UNWIND $rs AS rid MATCH (r:Kaynak {id: rid}) MERGE (o)-[:ETKILER]->(r)",
            id=proposal_id, tur=type_, durum=status, k=scope_id, rs=list(resource_ids),
        )

    def set_proposal_status(self, proposal_id: int, status: str) -> None:
        self._run("MATCH (o:Oneri {id: $id}) SET o.durum = $d", id=proposal_id, d=status)

    def record_decision(self, decision_id: int, topic_resource_id: str) -> None:
        self._run(
            "MERGE (k:Karar {id: $id}) WITH k MATCH (t:Konu {id: $t}) MERGE (k)-[:KONUSU]->(t)",
            id=decision_id, t=topic_resource_id,
        )

    def add_discourse_author(self, thread_id: int, user_id: str, first_at: datetime) -> None:
        self._run(
            "MERGE (d:Diskur {id: $d}) WITH d MATCH (u:User {id: $u}) "
            "MERGE (u)-[r:YAZDI]->(d) ON CREATE SET r.ilk = $t",
            d=thread_id, u=user_id, t=first_at,
        )

    def discourse_authors(self, thread_id: int) -> dict[str, datetime]:
        rows = self._run(
            "MATCH (u:User)-[r:YAZDI]->(:Diskur {id: $d}) RETURN u.id AS u, r.ilk AS t",
            d=thread_id,
        )
        return {r["u"]: _dt(r["t"]) for r in rows}

    def remove_discourse(self, thread_id: int) -> None:
        self._run("MATCH (d:Diskur {id: $d}) DETACH DELETE d", d=thread_id)
