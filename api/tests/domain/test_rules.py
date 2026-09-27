from dataclasses import replace
from datetime import UTC, datetime, timedelta

from mesveret.domain.regulation import Regulation
from mesveret.domain.rules import ProposalDraft, RuleContext, VoteRight, check_proposal
from mesveret.domain.types import ProposalType
from tests.domain.fixtures import sample_ontology

NOW = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
ONTO = sample_ontology()
REG = Regulation.defaults()
OK_RIGHT = VoteRight(True, None)


def ctx(**kw) -> RuleContext:
    base = {"onto": ONTO, "reg": REG, "now": NOW, "proposer_right": OK_RIGHT,
            "last_rejection": None}
    base.update(kw)
    return RuleContext(**base)


def konu(**kw) -> ProposalDraft:
    base = {
        "type": ProposalType.KONU, "proposer_id": "u1", "scope_id": "genel",
        "area_id": "sinema", "resource_ids": (), "title": "Film günleri", "body": "",
    }
    base.update(kw)
    return ProposalDraft(**base)


def rules_of(report) -> list[str]:
    return [v.rule for v in report.violations]


def test_valid_topic_passes():
    report = check_proposal(konu(), ctx())
    assert report.ok
    assert report.narrowings == []


# --- R1 --------------------------------------------------------------------------------------


def test_r1_subtopic_in_parent_area_or_its_subtree_passes():
    for area in ("sinema", "belgesel"):
        d = konu(type=ProposalType.ALT_KONU, parent_topic_id="konu:film-gunleri", area_id=area)
        assert check_proposal(d, ctx()).ok, area


def test_r1_subtopic_outside_parent_subtree_is_rejected():
    for area in ("edebiyat", "kultur"):
        d = konu(type=ProposalType.ALT_KONU, parent_topic_id="konu:film-gunleri", area_id=area)
        report = check_proposal(d, ctx())
        assert rules_of(report) == ["R1"], area
        assert "Sinema" in report.violations[0].message


# --- R2 --------------------------------------------------------------------------------------


def test_r2_owner_scope_decides_without_narrowing():
    report = check_proposal(konu(resource_ids=("butce",)), ctx())
    assert report.ok
    assert report.narrowings == []


def test_r2_subset_on_divisible_resource_is_narrowed_to_its_share():
    d = konu(scope_id="sehir:istanbul", resource_ids=("butce",), area_id="kent",
             title="Etkinlik bütçesinin tamamı İstanbul'a")
    report = check_proposal(d, ctx())
    assert report.ok
    [n] = report.narrowings
    assert n.resource_id == "butce"
    assert n.share == 4000
    assert n.message == "Bu karar yalnızca İstanbul payını etkiler (4.000 puan)."


def test_r2_subset_on_indivisible_resource_is_rejected():
    d = konu(scope_id="sehir:istanbul", resource_ids=("salon",), area_id="kent")
    report = check_proposal(d, ctx())
    assert rules_of(report) == ["R2"]
    assert report.violations[0].message.startswith("Bu kapsam bu kaynak hakkında karar veremez")


def test_r2_superset_scope_is_rejected():
    d = konu(scope_id="genel", resource_ids=("konu:ist-parklari",), area_id="kent")
    report = check_proposal(d, ctx())
    assert rules_of(report) == ["R2"]
    assert "sahibi İstanbul" in report.violations[0].message


def test_r2_unrelated_scope_is_rejected():
    d = konu(scope_id="ilgi:sinema", resource_ids=("konu:ist-parklari",), area_id="kent")
    assert rules_of(check_proposal(d, ctx())) == ["R2"]


def test_r2_subset_of_wrong_kind_cannot_take_a_city_share():
    d = konu(scope_id="ilgi:sinema", resource_ids=("butce",))
    report = check_proposal(d, ctx())
    assert rules_of(report) == ["R2"]
    assert "şehir" in report.violations[0].message


# --- R3 --------------------------------------------------------------------------------------


def test_r3_regulation_article_can_only_be_changed_by_regulation_proposal():
    report = check_proposal(konu(resource_ids=("madde:red_bekleme",)), ctx())
    assert "R3" in rules_of(report)


def test_r3_regulation_proposal_must_be_in_general_scope():
    d = konu(type=ProposalType.YONETMELIK, scope_id="sehir:istanbul", area_id=None,
             resource_ids=("madde:red_bekleme",))
    report = check_proposal(d, ctx())
    assert "R3" in rules_of(report)


def test_r3_valid_regulation_proposal_passes():
    d = konu(type=ProposalType.YONETMELIK, scope_id="genel", area_id=None,
             resource_ids=("madde:red_bekleme",))
    assert check_proposal(d, ctx()).ok


# --- R5 --------------------------------------------------------------------------------------


def test_r5_proposer_without_vote_right_in_scope_is_rejected():
    right = VoteRight(False, "Oy hakkınız 13.10.2026 tarihinde doğacak.")
    report = check_proposal(konu(scope_id="ilgi:sinema"), ctx(proposer_right=right))
    assert rules_of(report) == ["R5"]
    assert "13.10.2026" in report.violations[0].message


# --- R6 --------------------------------------------------------------------------------------


def test_r6_recently_rejected_target_is_blocked():
    report = check_proposal(konu(), ctx(last_rejection=NOW - timedelta(days=10)))
    assert rules_of(report) == ["R6"]


def test_r6_after_waiting_period_target_is_open_again():
    assert check_proposal(konu(), ctx(last_rejection=NOW - timedelta(days=30))).ok


def test_r6_waiting_period_is_read_from_regulation():
    reg = Regulation({**REG.values, "red_bekleme": {"gun": 5}})
    assert check_proposal(konu(), ctx(reg=reg, last_rejection=NOW - timedelta(days=6))).ok


# --- genel -----------------------------------------------------------------------------------


def test_all_violations_are_reported_together():
    d = replace(konu(scope_id="sehir:istanbul", resource_ids=("salon",)))
    report = check_proposal(
        d, ctx(proposer_right=VoteRight(False, "üye değil"), last_rejection=NOW)
    )
    assert set(rules_of(report)) == {"R2", "R5", "R6"}


def test_unknown_references_are_rejected_with_a_message():
    report = check_proposal(konu(scope_id="yok", area_id="yok", resource_ids=("yok",)), ctx())
    assert not report.ok
    assert all(v.message for v in report.violations)
