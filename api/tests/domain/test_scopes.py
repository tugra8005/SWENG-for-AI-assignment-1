from datetime import UTC, date, datetime, timedelta

from mesveret.domain.regulation import Regulation
from mesveret.domain.scopes import (
    Membership,
    MembershipReason,
    age_group,
    age_group_since,
    has_vote_right,
    vote_right_starts,
)

T0 = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
REG = Regulation.defaults()


def test_age_groups():
    today = date(2026, 9, 29)
    assert age_group(date(2010, 1, 1), today) is None  # 16 yaş
    assert age_group(date(2008, 9, 29), today) == "18-24"  # bugün 18
    assert age_group(date(2008, 9, 30), today) is None  # yarın 18
    assert age_group(date(2001, 9, 29), today) == "25-34"
    assert age_group(date(1991, 9, 30), today) == "25-34"  # yarın 35
    assert age_group(date(1977, 1, 1), today) == "35-49"
    assert age_group(date(1970, 1, 1), today) == "50+"


def test_age_group_since_is_the_birthday_that_entered_the_group():
    assert age_group_since(date(2001, 3, 15), "25-34") == date(2026, 3, 15)
    assert age_group_since(date(2000, 2, 29), "25-34") == date(2025, 3, 1)


def test_general_scope_right_is_immediate():
    m = Membership("genel", T0, MembershipReason.KAYIT)
    assert has_vote_right(m, T0, REG)


def test_interest_scope_waits_fourteen_days():
    m = Membership("ilgi:sinema", T0, MembershipReason.KATILIM)
    assert vote_right_starts(m, REG) == T0 + timedelta(days=14)
    assert not has_vote_right(m, T0 + timedelta(days=13, hours=23), REG)
    assert has_vote_right(m, T0 + timedelta(days=14), REG)


def test_city_scope_after_address_change_waits_ninety_days():
    m = Membership("sehir:istanbul", T0, MembershipReason.ADRES_DEGISIKLIGI)
    assert not has_vote_right(m, T0 + timedelta(days=89), REG)
    assert has_vote_right(m, T0 + timedelta(days=90), REG)


def test_city_scope_at_registration_is_immediate():
    m = Membership("sehir:istanbul", T0, MembershipReason.KAYIT)
    assert has_vote_right(m, T0, REG)


def test_waits_are_read_from_regulation():
    reg = Regulation({**REG.values, "ilgi_bekleme": {"gun": 1}})
    m = Membership("ilgi:sinema", T0, MembershipReason.KATILIM)
    assert has_vote_right(m, T0 + timedelta(days=1), reg)
