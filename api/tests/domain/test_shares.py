"""Bölünebilir kaynakta pay etkisi ve orantısızlık (R2'nin ters yönü)."""

from fractions import Fraction

from mesveret.domain.shares import share_impact

SHARES = {"sehir:istanbul": 4000, "sehir:ankara": 6000, "sehir:izmir": 5000, "sehir:bursa": 5000}


def test_half_of_istanbul_to_ankara_is_disproportionate_for_istanbul_only():
    imp = share_impact("butce", SHARES, {"sehir:istanbul": 2000, "sehir:ankara": 8000}, 10)
    assert imp.disproportionate == ("sehir:istanbul",)
    rows = {r.scope_id: r for r in imp.rows}
    assert rows["sehir:istanbul"].relative == Fraction(-1, 2)
    assert rows["sehir:izmir"].new == 5000 and rows["sehir:izmir"].relative == 0  # değişmeyen
    assert imp.average == Fraction(-1, 24)  # (-1/2 + 1/3 + 0 + 0) / 4
    assert imp.gap("sehir:istanbul") == Fraction(11, 24)  # ≈ 45,8 yüzde puanı


def test_equal_cut_for_everyone_is_not_disproportionate():
    cut = {k: v * 9 // 10 for k, v in SHARES.items()}
    imp = share_impact("butce", SHARES, cut, 10)
    assert imp.disproportionate == ()
    assert imp.average == Fraction(-1, 10)


def test_threshold_is_inclusive_in_percentage_points():
    two = {"a": 100, "b": 100}
    # a: -%20, b: 0 → ortalama -%10 → fark tam 10 puan
    assert share_impact("r", two, {"a": 80}, 10).disproportionate == ("a",)
    # a: -%18 → fark 9 puan
    assert share_impact("r", two, {"a": 82}, 10).disproportionate == ()
    assert share_impact("r", two, {"a": 82}, 9).disproportionate == ("a",)


def test_only_decreases_count_even_when_below_the_average_gain():
    imp = share_impact("r", {"a": 100, "b": 100, "c": 100}, {"a": 105, "b": 150, "c": 150}, 10)
    assert imp.disproportionate == ()


def test_scopes_with_zero_share_are_left_out_of_the_average():
    imp = share_impact("r", {"a": 0, "b": 100, "c": 100}, {"a": 50, "b": 50}, 10)
    rows = {r.scope_id: r for r in imp.rows}
    assert rows["a"].relative is None
    assert imp.average == Fraction(-1, 4)  # (-1/2 + 0) / 2
    assert imp.disproportionate == ("b",)
