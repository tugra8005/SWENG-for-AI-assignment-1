from datetime import timedelta
from fractions import Fraction

import pytest

from mesveret.domain.regulation import (
    DEFAULT_ARTICLES,
    Ratio,
    Regulation,
    RegulationError,
    validate_value,
)


def test_defaults_cover_every_article_in_the_spec():
    spec_keys = {
        "sessiz_onay_suresi", "itiraz_esigi", "basit_cogunluk", "yonetmelik_esigi",
        "red_bekleme", "musavir_esigi", "ilgi_bekleme", "adres_bekleme", "karar_saati",
        "kapanis_rakip_suresi", "yeniden_acma", "mahzen_kapasite", "mahzen_ust_sinir",
    }
    assert spec_keys <= set(DEFAULT_ARTICLES)


def test_simple_majority_is_strictly_more_than_half():
    ratio = Regulation.defaults().ratio("basit_cogunluk")
    assert not ratio.passes(5, 10)
    assert ratio.passes(6, 10)


def test_regulation_threshold_two_thirds_is_inclusive_and_exact():
    ratio = Regulation.defaults().ratio("yonetmelik_esigi")
    assert ratio.passes(20, 30)  # tam 2/3 geçer
    assert not ratio.passes(18, 30)  # %60 geçmez
    assert ratio.passes(67, 100)
    assert not ratio.passes(66, 100)


def test_ratio_with_no_votes_never_passes():
    assert not Ratio(Fraction(1, 2), ">").passes(0, 0)
    assert not Ratio(Fraction(0, 1), ">=").passes(0, 0)


def test_durations_are_read_from_articles():
    reg = Regulation.defaults()
    assert reg.duration("sessiz_onay_suresi") == timedelta(hours=24)
    assert reg.duration("red_bekleme") == timedelta(days=30)
    assert reg.duration("adres_bekleme") == timedelta(days=90)


def test_objection_threshold_is_max_of_minimum_and_percentage():
    reg = Regulation.defaults()
    assert reg.objection_threshold(active_members=10) == 3
    assert reg.objection_threshold(active_members=100) == 5
    assert reg.objection_threshold(active_members=101) == 6  # %5 yukarı yuvarlanır
    assert reg.objection_activity_window() == timedelta(days=30)


def test_values_come_from_the_given_mapping_not_constants():
    reg = Regulation({**Regulation.defaults().values, "musavir_esigi": {"deger": 2}})
    assert reg.integer("musavir_esigi") == 2


def test_validate_rejects_ratio_outside_bounds():
    with pytest.raises(RegulationError):
        validate_value("yonetmelik_esigi", {"oran": "2/5", "karsilastirma": ">="})
    with pytest.raises(RegulationError):
        validate_value("basit_cogunluk", {"oran": "3/2", "karsilastirma": ">"})


def test_validate_rejects_wrong_shape_and_unknown_article():
    with pytest.raises(RegulationError):
        validate_value("sessiz_onay_suresi", {"saat": -1})
    with pytest.raises(RegulationError):
        validate_value("mahzen_kapasite", {"deger": "yüz"})
    with pytest.raises(RegulationError):
        validate_value("olmayan_madde", {"deger": 1})


def test_validate_normalises_ratio_text():
    assert validate_value("yonetmelik_esigi", {"oran": "4/6", "karsilastirma": ">="}) == {
        "oran": "2/3",
        "karsilastirma": ">=",
    }


def test_decision_hour_spec():
    spec = Regulation.defaults().decision_hour()
    assert spec.weekday == 6  # Pazar
    assert (spec.hour, spec.minute) == (20, 0)
    assert spec.window == timedelta(minutes=60)
    assert spec.tz == "Europe/Istanbul"


def test_maturation_articles():
    reg = Regulation.defaults()
    assert reg.duration("olgunlasma_dar") == timedelta(hours=48)
    assert reg.duration("olgunlasma_genis") == timedelta(hours=72)
    assert reg.duration("olgunlasma_genel") == timedelta(days=7)


def test_every_default_validates():
    for key, article in DEFAULT_ARTICLES.items():
        assert validate_value(key, article.default) == article.default


# --- silme: içerik kuralları ve silme eşiği -------------------------------------------------------

REG = Regulation.defaults()


def test_deletion_threshold_is_two_thirds_inclusive():
    r = REG.ratio("silme_esigi")
    assert r.passes(20, 30) is True  # tam 2/3
    assert r.passes(18, 30) is False  # %60


def test_content_rules_are_the_three_narrow_seed_rules():
    rules = REG.content_rules()
    assert list(rules) == ["IK-1", "IK-2", "IK-3"]
    assert [r.title for r in rules.values()] == [
        "Spam ve reklam", "Hakaret ve tehdit", "Başkasının kişisel bilgilerini ifşa etme",
    ]
    assert all(r.text and r.keywords for r in rules.values())
    # "konu dışı" gibi geniş bir kural yok: sansür aracına dönüşür.
    assert not any("konu dışı" in r.title.lower() for r in rules.values())


def test_content_rule_is_a_text_article_that_validates():
    value = {"baslik": "Hakaret ve tehdit", "metin": "Kişiyi aşağılayan söz.",
             "anahtar_kelimeler": ["aptal", " cahil "]}
    assert validate_value("IK-2", value)["anahtar_kelimeler"] == ["aptal", "cahil"]
    for bad in ({**value, "anahtar_kelimeler": []}, {**value, "metin": " "},
                {**value, "anahtar_kelimeler": "aptal"}):
        with pytest.raises(RegulationError):
            validate_value("IK-2", bad)


def test_content_rules_can_be_added_and_removed_as_data():
    values = dict(REG.values)
    del values["IK-3"]
    values["IK-10"] = {"baslik": "Dolandırıcılık", "metin": "Sahte bağış ya da yatırım çağrısı.",
                       "anahtar_kelimeler": ["bağış", "yatırım"]}
    values["IK-4"] = {"baslik": "Tehlikeli sağlık tavsiyesi", "metin": "İlaç bırakma çağrısı.",
                      "anahtar_kelimeler": ["ilacı bırak"]}
    rules = Regulation(values).content_rules()
    assert list(rules) == ["IK-1", "IK-2", "IK-4", "IK-10"]  # numara sırasıyla
    assert validate_value("IK-10", values["IK-10"])["baslik"] == "Dolandırıcılık"
    for bad_key in ("IK-", "IK-x", "ik-4", "IK-04x"):
        with pytest.raises(RegulationError):
            validate_value(bad_key, values["IK-10"])


def test_disproportion_threshold_in_percentage_points():
    assert REG.number("orantisizlik_esigi") == 10
    assert validate_value("orantisizlik_esigi", {"deger": 12.5}) == {"deger": 12.5}
    with pytest.raises(RegulationError):
        validate_value("orantisizlik_esigi", {"deger": 150})
