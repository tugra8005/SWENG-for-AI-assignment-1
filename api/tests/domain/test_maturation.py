from datetime import UTC, datetime, timedelta

from mesveret.domain.maturation import (
    MaturityClass,
    first_session_at,
    matures_at,
    maturity_class,
    maturity_duration,
)
from mesveret.domain.regulation import Regulation
from mesveret.domain.types import ProposalType
from tests.domain.fixtures import sample_ontology

ONTO = sample_ontology()
REG = Regulation.defaults()
T0 = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)  # Salı 10:00 İstanbul


def klass(type_, scope_id):
    return maturity_class(ProposalType(type_), ONTO.scope(scope_id), ONTO)


def test_general_scope_and_regulation_are_general():
    assert klass("KONU", "genel") is MaturityClass.GENEL
    assert klass("SILME", "genel") is MaturityClass.GENEL
    assert klass("YONETMELIK", "genel") is MaturityClass.GENEL


def test_single_trait_scope_is_narrow():
    assert klass("KONU", "sehir:istanbul") is MaturityClass.DAR
    assert klass("KONU", "yas:25-34") is MaturityClass.DAR


def test_interest_scope_of_leaf_area_is_narrow_otherwise_wide():
    # sample_ontology: sinema → belgesel (yaprak); ilgi:sinema yaprak değil.
    from mesveret.domain.ontology import ScopeInfo
    from mesveret.domain.scopes import ScopeType

    assert klass("KONU", "ilgi:sinema") is MaturityClass.GENIS
    leaf = ScopeInfo("ilgi:belgesel", ScopeType.ILGI, "Belgesel (ilgi)", None, "belgesel")
    assert maturity_class(ProposalType.KONU, leaf, ONTO) is MaturityClass.DAR


def test_durations_come_from_regulation():
    assert maturity_duration(MaturityClass.DAR, REG) == timedelta(hours=48)
    assert maturity_duration(MaturityClass.GENIS, REG) == timedelta(hours=72)
    assert maturity_duration(MaturityClass.GENEL, REG) == timedelta(days=7)
    reg = Regulation({**REG.values, "olgunlasma_genel": {"gun": 2}})
    assert maturity_duration(MaturityClass.GENEL, reg) == timedelta(days=2)


def test_slow_lane_proposal_matures_from_publication():
    at = matures_at(ProposalType.SILME, created_at=T0, queued_at=T0,
                    klass=MaturityClass.GENEL, reg=REG)
    assert at == T0 + timedelta(days=7)


def test_fast_lane_proposal_that_fell_matures_from_the_fall():
    fell = T0 + timedelta(hours=20)
    at = matures_at(ProposalType.KONU, created_at=T0, queued_at=fell,
                    klass=MaturityClass.DAR, reg=REG)
    assert at == fell + timedelta(hours=48)


def test_first_session_is_the_first_scheduled_one_after_maturity():
    spec = REG.decision_hour()
    # 10 dakika önce açılan genel öneri: 7 gün sonra olgunlaşır; o haftanın Pazar oturumu
    # olgunlaşmadan önce kaldığı için bir sonraki Pazar'a kayar.
    opened = datetime(2026, 10, 4, 16, 50, tzinfo=UTC)  # Pazar 19:50 İstanbul
    mature = opened + timedelta(days=7)
    assert first_session_at(mature, opened, spec) == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)


def test_first_session_exactly_at_maturity_counts():
    spec = REG.decision_hour()
    mature = datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
    assert first_session_at(mature, T0, spec) == mature


def test_matured_proposal_goes_to_next_session_from_now():
    spec = REG.decision_hour()
    assert first_session_at(T0 - timedelta(days=3), T0, spec) == datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
