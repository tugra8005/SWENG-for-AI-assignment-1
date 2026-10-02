import pytest

from mesveret.domain import addressees
from mesveret.domain.ontology import ScopeInfo
from mesveret.domain.rules import check_proposal
from mesveret.domain.scopes import ScopeSubtype, ScopeType
from mesveret.domain.types import ProposalType
from tests.domain.fixtures import sample_ontology
from tests.domain.test_rules import ctx, konu, rules_of

ONTO = sample_ontology()
CITIES = ONTO.city_scopes()


def test_catalog_lists_calendar_municipalities_all_and_national_bodies():
    ids = [a.id for a in addressees.catalog(CITIES)]
    assert ids[0] == "takvim"
    assert ids[1:3] == ["belediye:ankara", "belediye:istanbul"]  # ada göre
    assert "belediyeler" in ids and "mesveret" not in ids
    assert {"bakanlik:ulastirma", "bakanlik:kultur", "bakanlik:cevre"} <= set(ids)


def test_municipality_names_follow_metropolitan_status():
    ist = addressees.lookup("belediye:istanbul", CITIES)
    assert ist and ist.name == "İstanbul Büyükşehir Belediyesi"
    tokat = ScopeInfo("sehir:tokat", ScopeType.NITELIK, "Tokat", ScopeSubtype.SEHIR, "Tokat")
    assert addressees.municipality(tokat).name == "Tokat Belediyesi"


def test_all_municipalities_expand_to_each_city():
    every = addressees.lookup("belediyeler", CITIES)
    assert every is not None
    assert [r.id for r in addressees.recipients(every, CITIES)] == [
        "belediye:ankara", "belediye:istanbul"]
    one = addressees.lookup("bakanlik:kultur", CITIES)
    assert one is not None and addressees.recipients(one, CITIES) == [one]


# Kapsam × muhatap matrisi (R9). Takvime her kapsam yazar.
ALLOWED = {
    "genel": {"takvim", "belediye:istanbul", "belediye:ankara", "belediyeler",
              "bakanlik:ulastirma", "bakanlik:kultur", "bakanlik:cevre"},
    "sehir:istanbul": {"takvim", "belediye:istanbul"},
    "yas:25-34": {"takvim", "bakanlik:ulastirma", "bakanlik:kultur", "bakanlik:cevre"},
    "ilgi:sinema": {"takvim", "bakanlik:ulastirma", "bakanlik:kultur", "bakanlik:cevre"},
}


@pytest.mark.parametrize("scope_id", sorted(ALLOWED))
def test_r9_jurisdiction_matrix(scope_id):
    for a in addressees.catalog(CITIES):
        d = konu(scope_id=scope_id, addressee=a.id, area_id="kent")
        report = check_proposal(d, ctx())
        r9 = [v for v in report.violations if v.rule == "R9"]
        assert (not r9) == (a.id in ALLOWED[scope_id]), (scope_id, a.id, r9)


def test_r9_messages_name_the_scope_and_the_body():
    report = check_proposal(konu(scope_id="sehir:istanbul", addressee="belediye:ankara",
                                 area_id="kent"), ctx())
    assert rules_of(report) == ["R9"]
    assert report.violations[0].message == (
        "İstanbul kapsamı yalnızca kendi belediyesine yazabilir; Ankara Büyükşehir Belediyesi bu "
        "kapsamın yetki alanında değil.")
    report = check_proposal(konu(scope_id="sehir:ankara", addressee="bakanlik:ulastirma",
                                 area_id="kent"), ctx())
    assert "ulusal kurumlara yazamaz" in report.violations[0].message


def test_r9_requires_an_addressee_and_refuses_internal_order():
    report = check_proposal(konu(addressee=None), ctx())
    assert rules_of(report) == ["R9"]
    assert report.violations[0].message.startswith("Muhatap seçilmeli")
    report = check_proposal(konu(addressee="mesveret"), ctx())
    assert "iç düzenine yazılamaz" in report.violations[0].message
    assert rules_of(check_proposal(konu(addressee="belediye:yok"), ctx())) == ["R9"]


def test_r9_applies_only_to_topic_proposals():
    d = konu(type=ProposalType.KAPANIS, addressee=None)
    assert "R9" not in rules_of(check_proposal(d, ctx()))
