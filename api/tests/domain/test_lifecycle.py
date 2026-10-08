import pytest

from mesveret.domain.lifecycle import (
    PENDING_STATUSES,
    InvalidTransition,
    opening_state,
    state_of,
)
from mesveret.domain.registry import Registry
from mesveret.domain.types import Lane, ProposalType


def test_opening_state_follows_type_and_lane():
    assert opening_state(ProposalType.KAPANIS, Lane.SLOW).status == "RIVAL_PERIOD"
    assert opening_state(ProposalType.KONU, Lane.FAST).status == "SILENT"
    assert opening_state(ProposalType.KONU, Lane.SLOW).status == "QUEUED"
    assert opening_state(ProposalType.SILME, Lane.SLOW).status == "QUEUED"


def test_silent_proposal_escalates_and_can_be_decided():
    s = state_of("SILENT")
    s.object()  # izinli: durum değişmez
    assert s.escalate().status == "QUEUED"
    assert s.escalate().enter_session().status == "VOTING"
    assert state_of("VOTING").accept().status == "ACCEPTED"
    assert state_of("VOTING").conflict().status == "CONFLICT"


def test_decided_states_are_final_with_reasons():
    for status in ("ACCEPTED", "REJECTED", "CONFLICT"):
        s = state_of(status)
        assert not s.pending
        with pytest.raises(InvalidTransition, match="zaten karara bağlandı"):
            s.accept()
        with pytest.raises(InvalidTransition, match="itiraza açık değil"):
            s.object()


def test_only_rival_period_takes_rival_texts_and_only_drafts_are_submitted():
    state_of("RIVAL_PERIOD").add_rival()
    with pytest.raises(InvalidTransition, match="Rakip metin süresi doldu"):
        state_of("QUEUED").add_rival()
    state_of("DRAFT").submit()
    with pytest.raises(InvalidTransition, match="taslak değil"):
        state_of("SILENT").submit()
    with pytest.raises(InvalidTransition):
        state_of("QUEUED").escalate()


def test_pending_statuses_are_the_undecided_ones():
    assert set(PENDING_STATUSES) == {"SILENT", "RIVAL_PERIOD", "QUEUED", "VOTING"}


def test_registry_creates_by_key_and_refuses_duplicates():
    reg = Registry[object]("deneme")

    @reg.register("a")
    class A:
        def __init__(self, x=1):
            self.x = x

    assert reg.create("a", x=5).x == 5 and "a" in reg and list(reg) == ["a"]
    with pytest.raises(KeyError, match="zaten kayıtlı"):
        reg.register("a")(A)
    with pytest.raises(KeyError, match="Seçenekler: a"):
        reg.create("b")
