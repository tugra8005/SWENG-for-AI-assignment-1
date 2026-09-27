from mesveret.domain.oracle import label_check, oracle_comment, oracle_vote
from mesveret.domain.rules import RuleReport, Violation
from mesveret.domain.text import normalize, tokens
from tests.domain.fixtures import sample_ontology

ONTO = sample_ontology()


def check(text, area_id="sinema", scope_id="genel", resource_ids=()):
    return label_check(text, area_id, scope_id, tuple(resource_ids), ONTO)


def kinds(findings):
    return [f.kind for f in findings]


def test_turkish_genitive_follows_vowel_harmony():
    from mesveret.domain.text import genitive

    assert genitive("Etkinlik bütçesi") == "Etkinlik bütçesinin"
    assert genitive("Ortak toplantı salonu") == "Ortak toplantı salonunun"
    assert genitive("Kent parkı") == "Kent parkının"
    assert genitive("Gül bahçesi") == "Gül bahçesinin"
    assert genitive("Yol") == "Yolun"
    assert genitive("Köprü") == "Köprünün"


def test_turkish_normalisation():
    assert normalize("İSTANBUL'a IŞIK") == "istanbula ışık"
    assert tokens("Bütçe'nin %10'u, İzmir!") == ["bütçenin", "10u", "izmir"]


# --- H1 alan ---------------------------------------------------------------------------------


def test_h1_suggests_best_matching_area():
    findings = check("Belgesel gösterimi: her ay bir belgesel", area_id="kent")
    assert kinds(findings) == ["H1"]
    assert findings[0].suggestion == "belgesel"


def test_h1_accepts_ancestor_of_best_area():
    assert check("Belgesel gösterimi: her ay bir belgesel", area_id="sinema") == []


def test_h1_needs_at_least_two_hits():
    assert check("Bir belgesel", area_id="kent") == []


def test_h1_tie_gives_no_suggestion():
    assert check("roman roman bisiklet bisiklet", area_id="belgesel") == []


# --- H2 etiketlenmemiş kaynak ----------------------------------------------------------------


def test_h2_flags_mentioned_but_unlabelled_resource():
    findings = check("Etkinlik bütçesinin yarısı festivale", area_id="kent")
    assert kinds(findings) == ["H2"]
    assert findings[0].suggestion == "butce"


def test_h2_is_silent_when_resource_is_labelled():
    assert check("Etkinlik bütçesinin yarısı", area_id="kent", resource_ids=["butce"]) == []


# --- H3 şehir --------------------------------------------------------------------------------


def test_h3_flags_single_city_mentioned_with_other_city_scope():
    findings = check("Ankara'da buluşalım", area_id="kent", scope_id="sehir:istanbul")
    assert kinds(findings) == ["H3"]
    assert findings[0].suggestion == "sehir:ankara"


def test_h3_is_silent_for_general_scope_or_several_cities():
    assert check("Ankara'da buluşalım", area_id="kent", scope_id="genel") == []
    assert check("Ankara ve İstanbul", area_id="kent", scope_id="sehir:istanbul") == []


def test_h3_is_silent_when_city_matches_scope():
    assert check("İstanbul'da buluşalım", area_id="kent", scope_id="sehir:istanbul") == []


# --- oy ve yorum -----------------------------------------------------------------------------


def test_vote_yes_only_when_rules_pass_and_labels_agree():
    ok = RuleReport()
    bad = RuleReport(violations=[Violation("R6", "…")])
    finding = check("Belgesel gösterimi: her ay bir belgesel", area_id="kent")
    assert oracle_vote(ok, []) is True
    assert oracle_vote(ok, finding) is False
    assert oracle_vote(bad, []) is False


def test_comment_mentions_suggestions_in_turkish():
    findings = check("Etkinlik bütçesinin yarısı. Belgesel belgesel", area_id="kent")
    text = oracle_comment(RuleReport(), findings, ONTO)
    assert "Etiket önerisi" in text
    assert "Etkinlik bütçesi" in text
    assert "Belgesel" in text


def test_comment_when_everything_agrees():
    text = oracle_comment(RuleReport(), [], ONTO)
    assert "uyumlu" in text


def test_comment_explains_narrowing():
    from mesveret.domain.rules import Narrowing

    report = RuleReport(narrowings=[Narrowing(
        "butce", "sehir:istanbul", 4000, "Bu karar yalnızca İstanbul payını etkiler (4.000 puan).",
        total=7000, effect_title="Etkinlik bütçesinin İstanbul payı",
    )])
    text = oracle_comment(report, [], ONTO)
    assert ("Talep kaynağın tamamını hedefliyordu; seçmen kapsamı yalnızca İstanbul payına "
            "karar verebilir, daraltma uygulandı.") in text
