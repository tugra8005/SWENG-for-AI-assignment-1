"""Türkçe sayı biçimi: bütün yüzdeler tek yardımcıdan geçer."""

from mesveret.domain.shares import pct, pp
from mesveret.domain.text import percent_tr


def test_sign_goes_before_the_percent_sign():
    assert percent_tr(-50) == "-%50,0"
    assert percent_tr(-4.2) == "-%4,2"
    assert percent_tr(33.333) == "%33,3"
    assert percent_tr(-0.01) == "%0,0"  # yuvarlanınca sıfır: eksi yok


def test_compact_drops_a_zero_fraction_only():
    assert percent_tr(50, compact=True) == "%50"
    assert percent_tr(66.667, compact=True) == "%66,7"


def test_share_helpers_use_the_same_format():
    from fractions import Fraction

    assert pct(Fraction(-1, 2)) == "-%50,0"
    assert pp(Fraction(11, 24)).startswith("45,8")
