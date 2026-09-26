from tests.domain.fixtures import sample_ontology


def test_ancestors_start_with_self_and_end_at_root():
    onto = sample_ontology()
    assert onto.area_ancestors("belgesel") == ["belgesel", "sinema", "kultur"]
    assert onto.area_ancestors("kent") == ["kent"]


def test_subtree_includes_self_and_all_descendants():
    onto = sample_ontology()
    assert onto.area_subtree("kultur") == {"kultur", "sinema", "belgesel", "edebiyat"}
    assert onto.area_subtree("belgesel") == {"belgesel"}


def test_scope_subset_relation_is_ontological_and_strict():
    onto = sample_ontology()
    assert onto.is_strict_subset("sehir:istanbul", "genel")
    assert not onto.is_strict_subset("genel", "sehir:istanbul")
    assert not onto.is_strict_subset("sehir:istanbul", "sehir:istanbul")
    assert not onto.is_strict_subset("sehir:istanbul", "ilgi:sinema")


def test_unknown_lookups_return_none():
    onto = sample_ontology()
    assert onto.area("yok") is None
    assert onto.scope("yok") is None
    assert onto.resource("yok") is None
