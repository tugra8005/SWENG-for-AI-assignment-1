"""Bölünebilir kaynakta pay etkisi ve orantısızlık (R2'nin ters yönü).

R2, bir alt kapsamın bütünün kaynağı hakkında karar vermesini engeller. Bu modül ters yönü
ölçer: bütünün (ör. Genel) bir alt kapsamın payını gasp etmesi. Öneri etkisini kapsam başına
yeni paylarla bildirir; her alt kapsamın göreli değişimi (yeni - eski) / eski hesaplanır.
Bir alt kapsamın payı azalıyor ve bu azalma tüm alt kapsamların ortalama göreli değişiminden
en az ``orantisizlik_esigi`` yüzde puanı fazlaysa o kapsam "orantısız etkilenen" sayılır.
Herkese eşit oranda kesinti orantısız değildir. Orantısız etkilenen her kapsamda ayrı oylama
yapılır; öneri hepsinde çoğunluk almalıdır (eşzamanlı çoğunluk).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from mesveret.domain.text import decimal_tr


@dataclass(frozen=True)
class ShareRow:
    scope_id: str
    old: int
    new: int
    relative: Fraction | None  # eski pay 0 ise tanımsız

    @property
    def changed(self) -> bool:
        return self.old != self.new


@dataclass(frozen=True)
class ShareImpact:
    resource_id: str
    rows: tuple[ShareRow, ...]
    average: Fraction | None  # payı olan alt kapsamların ortalama göreli değişimi
    threshold_pp: Fraction
    disproportionate: tuple[str, ...]

    def gap(self, scope_id: str) -> Fraction | None:
        """Kapsamın göreli değişiminin ortalamanın ne kadar altında kaldığı (oran olarak)."""
        row = next((r for r in self.rows if r.scope_id == scope_id), None)
        if row is None or row.relative is None or self.average is None:
            return None
        return self.average - row.relative

    @property
    def changed(self) -> bool:
        return any(r.changed for r in self.rows)


def share_impact(resource_id: str, old_shares: Mapping[str, int], effect: Mapping[str, int],
                 threshold_pp: float | Fraction) -> ShareImpact:
    rows = []
    for scope_id, old in old_shares.items():
        new = int(effect.get(scope_id, old))
        rel = Fraction(new - old, old) if old > 0 else None
        rows.append(ShareRow(scope_id, int(old), new, rel))
    known = [r.relative for r in rows if r.relative is not None]
    average = sum(known, Fraction(0)) / len(known) if known else None
    threshold = Fraction(threshold_pp) / 100
    flagged = tuple(
        r.scope_id for r in rows
        if average is not None and r.relative is not None and r.relative < 0
        and average - r.relative >= threshold
    )
    return ShareImpact(resource_id, tuple(rows), average, Fraction(threshold_pp), flagged)


def pct(ratio: Fraction | None) -> str:
    """Göreli değişim yüzde olarak, Türkçe ondalıkla: -1/2 → "-50,0"."""
    return "—" if ratio is None else decimal_tr(float(ratio) * 100)


def _number(x: Fraction) -> str:
    return str(int(x)) if x.denominator == 1 else decimal_tr(float(x))


def points(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def impact_lines(impacts: Sequence[ShareImpact], scope_name: Callable[[str], str]) -> list[str]:
    """Hâtif'in öneri altındaki yorumu için: orantısız etkilenen kapsamlar."""
    lines: list[str] = []
    affected: list[str] = []
    for imp in impacts:
        for sid in imp.disproportionate:
            row = next(r for r in imp.rows if r.scope_id == sid)
            affected.append(scope_name(sid))
            lines.append(
                f"Orantısız etkilenen kapsam: {scope_name(sid)} — pay {points(row.old)} → "
                f"{points(row.new)} (%{pct(row.relative)}); alt kapsamların ortalama değişimi "
                f"%{pct(imp.average)}, fark {pct(imp.gap(sid))} yüzde puanı "
                f"(eşik {_number(imp.threshold_pp)})."
            )
    if affected:
        names = ", ".join(dict.fromkeys(affected))
        lines.append(f"Karar Saati'nde {names} seçmenleri ayrıca oylar; öneri her oylamada "
                     "gerekli çoğunluğu almalı (eşzamanlı çoğunluk).")
    elif impacts:
        avg = ", ".join(f"%{pct(imp.average)}" for imp in impacts)
        lines.append(f"Pay etkisi: orantısız etkilenen kapsam yok (ortalama değişim {avg}); "
                     "tek oylama.")
    return lines
