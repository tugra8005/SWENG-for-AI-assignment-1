"""GraphStore sözleşme testleri.

Aynı testler bellek içi grafa (her zaman) ve Neo4j'ye (test yığını ayaktayken) karşı
çalışır: ``tests/test_graph_memory.py`` ve ``tests/integration/test_graph_neo4j.py``.
"""

from datetime import UTC, datetime, timedelta

import pytest

from mesveret.domain.ontology import AreaInfo, ResourceInfo, ResourceKind, ScopeInfo
from mesveret.domain.scopes import Membership, MembershipReason, ScopeSubtype, ScopeType

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def build(g) -> None:
    g.reset()
    g.upsert_area(AreaInfo("kultur", "Kültür", None, ("kültür",)))
    g.upsert_area(AreaInfo("sinema", "Sinema", "kultur", ("sinema", "film")))
    g.upsert_area(AreaInfo("belgesel", "Belgesel", "sinema", ("belgesel",)))
    g.upsert_area(AreaInfo("kent", "Kent", None, ("kent",)))
    g.upsert_scope(ScopeInfo("genel", ScopeType.GENEL, "Genel"), set())
    g.upsert_scope(
        ScopeInfo("sehir:istanbul", ScopeType.NITELIK, "İstanbul", ScopeSubtype.SEHIR, "İstanbul"),
        {"genel"},
    )
    g.upsert_scope(ScopeInfo("ilgi:sinema", ScopeType.ILGI, "Sinema", None, "sinema"), {"genel"})
    g.upsert_resource(ResourceInfo(
        "butce", ResourceKind.ORTAK, "Etkinlik bütçesi", "genel", True, ScopeSubtype.SEHIR,
        {"sehir:istanbul": 4000}, ("bütçe",),
    ))
    g.upsert_resource(
        ResourceInfo("konu:1", ResourceKind.KONU, "Film günleri", "ilgi:sinema"),
        topic_area_id="sinema",
    )
    for uid, nick in (("a", "ayse"), ("b", "bora"), ("c", "cem")):
        g.upsert_user(uid, nick, "CITIZEN", T0)


class GraphContract:
    """Alt sınıf ``graph`` fikstürünü sağlar."""

    @pytest.fixture
    def g(self, graph):
        build(graph)
        return graph

    # --- ontoloji ---
    def test_area_tree(self, g):
        assert g.area_ancestors("belgesel") == ["belgesel", "sinema", "kultur"]
        assert g.area_subtree("kultur") == {"kultur", "sinema", "belgesel"}
        assert g.area_descendants_bfs("kultur") == ["kultur", "sinema", "belgesel"]
        assert g.all_area_ids_bfs() == ["kent", "kultur", "sinema", "belgesel"]
        assert g.area("sinema").keywords == ("sinema", "film")

    def test_scopes_and_subset(self, g):
        assert g.scope("sehir:istanbul").subtype is ScopeSubtype.SEHIR
        assert g.is_strict_subset("sehir:istanbul", "genel")
        assert not g.is_strict_subset("genel", "sehir:istanbul")
        assert [s.id for s in g.city_scopes()] == ["sehir:istanbul"]

    def test_resources(self, g):
        r = g.resource("butce")
        assert r.divisible and r.division_type is ScopeSubtype.SEHIR
        assert dict(r.shares) == {"sehir:istanbul": 4000}
        assert r.aliases == ("bütçe",)
        assert g.topic_area("konu:1") == "sinema"
        assert {x.id for x in g.all_resources()} == {"butce", "konu:1"}

    def test_upsert_resource_updates_owner(self, g):
        g.upsert_resource(ResourceInfo("konu:1", ResourceKind.KONU, "Film günleri", "genel"),
                          topic_area_id="sinema")
        assert g.resource("konu:1").owner_scope_id == "genel"

    # --- üyelik ---
    def test_memberships(self, g):
        g.set_membership("a", Membership("genel", T0, MembershipReason.KAYIT))
        g.set_membership("a", Membership("ilgi:sinema", T0, MembershipReason.KATILIM))
        g.set_membership("b", Membership("genel", T0, MembershipReason.KAYIT))
        assert {m.scope_id for m in g.memberships("a")} == {"genel", "ilgi:sinema"}
        members = g.scope_members("genel")
        assert set(members) == {"a", "b"}
        assert members["a"].since == T0
        assert members["a"].reason is MembershipReason.KAYIT
        g.remove_membership("a", "ilgi:sinema")
        assert g.scope_members("ilgi:sinema") == {}

    def test_membership_update_replaces_since(self, g):
        g.set_membership("a", Membership("genel", T0, MembershipReason.KAYIT))
        later = T0 + timedelta(days=3)
        g.set_membership("a", Membership("genel", later, MembershipReason.KAYIT))
        assert g.scope_members("genel")["a"].since == later

    # --- havale ---
    def test_delegations(self, g):
        g.set_delegation("a", "b", None, T0)
        g.set_delegation("a", "c", "sinema", T0)
        g.set_delegation("b", "c", "sinema", T0)
        assert g.delegations() == {("a", None): "b", ("a", "sinema"): "c", ("b", "sinema"): "c"}
        assert g.incoming_delegations("c") == {"sinema": 2}
        assert g.incoming_delegations("b") == {None: 1}
        g.set_delegation("a", "b", "sinema", T0)  # aynı alanda yenisi eskisinin yerine geçer
        assert g.delegations()[("a", "sinema")] == "b"
        assert g.remove_delegation("a", "sinema")
        assert not g.remove_delegation("a", "sinema")
        assert ("a", "sinema") not in g.delegations()
        outgoing = g.outgoing_delegations("a")
        assert [(area, target) for area, target, _ in outgoing] == [(None, "b")]

    # --- etkileşim ---
    def test_interactions_accumulate(self, g):
        g.add_interaction("a", "b", 1.0)
        g.add_interaction("a", "b", 0.5)
        g.add_interaction("b", "c", 2.0)
        assert g.interactions_among({"a", "b"}) == {("a", "b"): 1.5}
        assert g.interactions_among({"a", "b", "c"}) == {("a", "b"): 1.5, ("b", "c"): 2.0}

    # --- yönetmelik ---
    def test_articles(self, g):
        g.set_article("red_bekleme", {"gun": 30})
        g.set_article("red_bekleme", {"gun": 10})
        assert g.articles()["red_bekleme"] == {"gun": 10}

    # --- öneri, karar, diskur ---
    def test_proposal_and_discourse_records(self, g):
        g.record_proposal(7, "KONU", "genel", ["butce"], "SILENT")
        g.set_proposal_status(7, "ACCEPTED")
        g.record_decision(3, "konu:1")
        g.add_discourse_author(5, "a", T0)
        g.add_discourse_author(5, "b", T0)
        assert g.discourse_authors(5) == {"a": T0, "b": T0}
        g.remove_discourse(5)
        assert g.discourse_authors(5) == {}

    def test_reset_clears_everything(self, g):
        g.reset()
        assert g.all_areas() == []
        assert g.delegations() == {}
