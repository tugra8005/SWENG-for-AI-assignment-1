from datetime import timedelta
from fractions import Fraction

import pytest

from mesveret.domain.regulation import (
    ARTICLE_META,
    DEFAULT_ARTICLES,
    PARAMETER_GROUPS,
    Ratio,
    Regulation,
    RegulationError,
    article_title,
    describe_range,
    range_violations,
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
        validate_value("basit_cogunluk", {"oran": "2/5", "karsilastirma": ">"})
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



# --- değiştirilemez maddeler ve tabanlar ---------------------------------------------------------


def test_unchangeable_articles_are_the_seven_principles():
    principles = [k for k, a in DEFAULT_ARTICLES.items() if a.kind == "temel_ilke"]
    assert principles == [f"D{i}" for i in range(1, 8)]
    assert REG.raw("D3")["baslik"] == "Kaybeden taraf Şerh ekleyebilir; Şerh silinemez."
    assert REG.raw("D7")["baslik"] == "Bu listenin kendisi."
    assert "izinli aralık" in REG.raw("D7")["metin"]
    assert REG.unchangeable == frozenset(principles)
    assert not REG.is_unchangeable("yonetmelik_esigi")  # değer değişir, aralığı değişmez


NUMERIC_KINDS = {"sure", "oran", "tamsayi", "sayi", "yuzde_puani", "itiraz", "karar_saati",
                 "agirliklar"}


def test_every_numeric_parameter_has_a_range_and_defaults_lie_inside():
    for key, a in DEFAULT_ARTICLES.items():
        if a.kind in NUMERIC_KINDS:
            assert a.allowed, key
            assert range_violations(key, a.default) == [], key
        else:
            assert not a.allowed, key


def test_ranges_from_the_task():
    ok = {
        "basit_cogunluk": [{"oran": "1/2", "karsilastirma": ">"}, {"oran": "2/3", "karsilastirma": ">="}],
        "yonetmelik_esigi": [{"oran": "2/3", "karsilastirma": ">="}, {"oran": "3/4", "karsilastirma": ">="}],
        "silme_esigi": [{"oran": "7/10", "karsilastirma": ">="}],
        "sessiz_onay_suresi": [{"saat": 12}, {"saat": 72}, {"gun": 3}],
        "itiraz_esigi": [{"min": 3, "oran": "1/50", "aktiflik_gun": 30},
                         {"min": 3, "oran": "1/5", "aktiflik_gun": 30},
                         {"min": 20, "oran": "1/20", "aktiflik_gun": 30}],
        "red_bekleme": [{"gun": 7}, {"gun": 90}],
        "olgunlasma_genel": [{"saat": 24}, {"gun": 14}],
        "ilgi_bekleme": [{"gun": 0}, {"gun": 30}],
        "adres_bekleme": [{"gun": 0}, {"gun": 180}],
        "orantisizlik_esigi": [{"deger": 5}, {"deger": 30}],
        "musavir_esigi": [{"deger": 3}, {"deger": 50}],
        "kapanis_rakip_suresi": [{"saat": 24}, {"gun": 7}],
        "yeniden_acma": [{"gun": 30}, {"gun": 365}],
        "havale_suresi": [{"gun": 30}, {"gun": 180}, {"gun": 365}],
        "havale_uyari_suresi": [{"gun": 3}, {"gun": 14}, {"gun": 30}],
    }
    bad = {
        "basit_cogunluk": [{"oran": "1/2", "karsilastirma": ">="}, {"oran": "3/4", "karsilastirma": ">="}],
        "yonetmelik_esigi": [{"oran": "1/2", "karsilastirma": ">="}, {"oran": "4/5", "karsilastirma": ">="},
                             {"oran": "3/4", "karsilastirma": ">"}],
        "silme_esigi": [{"oran": "3/5", "karsilastirma": ">"}],
        "sessiz_onay_suresi": [{"saat": 11}, {"gun": 4}],
        "itiraz_esigi": [{"min": 3, "oran": "1/100", "aktiflik_gun": 30},
                         {"min": 3, "oran": "1/4", "aktiflik_gun": 30},
                         {"min": 1, "oran": "1/20", "aktiflik_gun": 30},  # tek kişi yavaş şeride iter
                         {"min": 2, "oran": "1/20", "aktiflik_gun": 30},
                         {"min": 21, "oran": "1/20", "aktiflik_gun": 30}],
        "red_bekleme": [{"gun": 6}, {"gun": 91}],
        "olgunlasma_dar": [{"saat": 23}, {"gun": 15}],
        "ilgi_bekleme": [{"gun": 31}],
        "adres_bekleme": [{"gun": 181}],
        "orantisizlik_esigi": [{"deger": 4}, {"deger": 31}],
        "musavir_esigi": [{"deger": 2}, {"deger": 51}],
        "kapanis_rakip_suresi": [{"saat": 23}, {"gun": 8}],
        "yeniden_acma": [{"gun": 29}, {"gun": 366}],
        "havale_suresi": [{"gun": 29}, {"gun": 366}, {"saat": 24}],
        "havale_uyari_suresi": [{"gun": 2}, {"gun": 31}],
    }
    for key, values in ok.items():
        for v in values:
            assert range_violations(key, validate_value(key, v)) == [], (key, v)
    for key, values in bad.items():
        for v in values:
            assert range_violations(key, validate_value(key, v)), (key, v)


def test_range_descriptions_are_readable():
    text = {k: describe_range(k) for k in DEFAULT_ARTICLES}
    assert text["basit_cogunluk"] == "> 1/2 – ≥ 2/3"
    assert text["yonetmelik_esigi"] == "≥ 2/3 – ≥ 3/4"
    assert text["sessiz_onay_suresi"] == "12 saat – 72 saat"
    assert text["olgunlasma_genel"] == "24 saat – 14 gün"
    assert text["ilgi_bekleme"] == "0 – 30 gün"
    assert text["itiraz_esigi"] == "en az 3–20 itiraz · oran %2 – %20 · aktiflik 7–90 gün"
    assert text["orantisizlik_esigi"] == "5 – 30 yüzde puanı"
    assert text["havale_suresi"] == "30 – 365 gün"
    assert text["havale_uyari_suresi"] == "3 – 30 gün"
    assert text["D1"] is None


def test_zero_duration_is_valid_shape_but_ranges_decide():
    assert validate_value("ilgi_bekleme", {"gun": 0}) == {"gun": 0}
    assert range_violations("sessiz_onay_suresi", {"saat": 0})


def test_principle_values_validate():
    assert validate_value("D1", REG.raw("D1")) == REG.raw("D1")


def test_every_parameter_has_a_readable_title_and_a_group():
    params = {k for k, a in DEFAULT_ARTICLES.items()
              if not a.unchangeable and a.kind != "icerik_kurali"}
    assert set(ARTICLE_META) == params
    for key, (title, group) in ARTICLE_META.items():
        assert group in PARAMETER_GROUPS, key
        assert title and "_" not in title, key
    assert article_title("sessiz_onay_suresi") == "Sessiz onay süresi"
    assert article_title("IK-2", {"baslik": "Hakaret ve tehdit"}) == "IK-2 Hakaret ve tehdit"
    assert Ratio(Fraction(2, 3), ">=").describe() == "en az 2/3 (%66,7)"
    assert Ratio(Fraction(1, 2), ">").describe() == "1/2 (%50) — fazlası"
