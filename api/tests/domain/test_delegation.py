import pytest

from mesveret.domain.delegation import (
    DelegationCycleError,
    SelfDelegationError,
    can_vote,
    check_new_delegation,
    effective_delegate,
    resolve_all,
    resolve_terminal,
)
from tests.domain.fixtures import sample_ontology

ONTO = sample_ontology()


# --- çözümleme ve miras ------------------------------------------------------------------


def test_no_delegation_means_no_delegate():
    assert effective_delegate({}, "a", "sinema", ONTO) is None


def test_general_delegation_applies_to_every_area_and_to_arealess_proposals():
    d = {("a", None): "b"}
    assert effective_delegate(d, "a", "sinema", ONTO) == "b"
    assert effective_delegate(d, "a", "kent", ONTO) == "b"
    assert effective_delegate(d, "a", None, ONTO) == "b"


def test_area_delegation_overrides_general_in_that_area():
    d = {("a", None): "b", ("a", "sinema"): "c"}
    assert effective_delegate(d, "a", "sinema", ONTO) == "c"
    assert effective_delegate(d, "a", "kent", ONTO) == "b"


def test_child_area_inherits_parent_delegation():
    d = {("a", "kultur"): "c"}
    assert effective_delegate(d, "a", "belgesel", ONTO) == "c"
    assert effective_delegate(d, "a", "kent", ONTO) is None


def test_more_specific_child_delegation_wins_over_parent():
    d = {("a", "kultur"): "c", ("a", "sinema"): "d"}
    assert effective_delegate(d, "a", "belgesel", ONTO) == "d"
    assert effective_delegate(d, "a", "edebiyat", ONTO) == "c"


def test_area_delegation_does_not_apply_to_arealess_proposals():
    d = {("a", "sinema"): "c"}
    assert effective_delegate(d, "a", None, ONTO) is None


def test_chain_is_followed_to_the_end():
    d = {("a", None): "b", ("b", "sinema"): "c"}
    assert resolve_terminal(d, "a", "sinema", ONTO) == ("c", ["a", "b", "c"])
    assert resolve_terminal(d, "a", "kent", ONTO) == ("b", ["a", "b"])


def test_delegator_cannot_vote_in_that_area():
    d = {("a", "sinema"): "b"}
    assert not can_vote(d, "a", "belgesel", ONTO)
    assert can_vote(d, "a", "kent", ONTO)
    assert can_vote(d, "b", "sinema", ONTO)


# --- döngü kontrolü (R4) --------------------------------------------------------------------


def test_self_delegation_is_rejected():
    with pytest.raises(SelfDelegationError):
        check_new_delegation({}, "a", "a", "sinema", ONTO)


def test_direct_cycle_is_rejected():
    with pytest.raises(DelegationCycleError) as err:
        check_new_delegation({("b", "sinema"): "a"}, "a", "b", "sinema", ONTO)
    assert err.value.area_id == "sinema"


def test_long_cycle_is_rejected():
    d = {("b", None): "c", ("c", None): "a"}
    with pytest.raises(DelegationCycleError):
        check_new_delegation(d, "a", "b", None, ONTO)


def test_opposite_delegations_in_unrelated_areas_are_allowed():
    check_new_delegation({("b", "kent"): "a"}, "a", "b", "sinema", ONTO)


def test_cycle_through_inheritance_in_child_area_is_rejected():
    # v, Sinema'da u'ya havale etmiş. u, Kültür'de v'ye havale ederse Sinema'da
    # u'nun etkin temsilcisi v olur (miras) ve Sinema'da döngü oluşur.
    d = {("v", "sinema"): "u"}
    with pytest.raises(DelegationCycleError) as err:
        check_new_delegation(d, "u", "v", "kultur", ONTO)
    assert err.value.area_id == "sinema"


def test_general_delegation_cycle_through_area_delegation_is_rejected():
    d = {("v", "belgesel"): "u"}
    with pytest.raises(DelegationCycleError) as err:
        check_new_delegation(d, "u", "v", None, ONTO)
    assert err.value.area_id == "belgesel"


def test_inherited_cycle_is_ignored_when_a_more_specific_delegation_breaks_it():
    # u'nun Sinema'da kendi havalesi (w'ye) var; Kültür havalesi Sinema'da etkili olmaz.
    d = {("v", "sinema"): "u", ("u", "sinema"): "w"}
    check_new_delegation(d, "u", "v", "kultur", ONTO)


def test_replacing_a_delegation_is_checked_against_the_new_state():
    # a→b vardı; a→c ile değiştirmek, eski a→b'nin oluşturacağı döngüden bağımsızdır.
    d = {("a", "sinema"): "b", ("c", "sinema"): "d"}
    check_new_delegation(d, "a", "c", "sinema", ONTO)


# --- anlık görüntü için toplu çözümleme ------------------------------------------------------


def test_resolve_all_maps_everyone_to_their_terminal():
    d = {("a", None): "b", ("b", None): "c"}
    resolved = resolve_all(d, "sinema", ONTO, ["a", "b", "c", "e"])
    assert resolved == {"a": "c", "b": "c", "c": "c", "e": "e"}


def test_resolve_all_passes_through_users_outside_the_list():
    d = {("a", None): "x", ("x", None): "c"}
    assert resolve_all(d, "sinema", ONTO, ["a", "c"]) == {"a": "c", "c": "c"}
