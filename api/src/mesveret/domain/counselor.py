"""Müşavir: bir alanda eşik sayıda doğrudan havale almış yurttaş (atanmaz, kendiliğinden doğar)."""

from collections.abc import Mapping

from mesveret.domain.regulation import Regulation


def counselor_areas(incoming: Mapping[str | None, int], reg: Regulation) -> list[str]:
    threshold = reg.integer("musavir_esigi")
    return sorted(a for a, n in incoming.items() if a is not None and n >= threshold)
