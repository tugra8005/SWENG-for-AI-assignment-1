"""Baskın tespiti.

Seçmen anlık görüntüsü alınırken çalışır:
1. Aday: katılım anı anlık görüntüden en fazla ``baskin_yeni_uye_suresi`` önce olan seçmen.
2. Adaylar arasında iki yönlü toplam ETKILESIM ağırlığı ``baskin_min_agirlik`` ve üstü
   olan çiftler yönsüz kenar olur.
3. Bağlı bileşenlerden boyutu, yoğunluğu ve katılım yayılımı eşikleri sağlayanlar
   işaretlenir. İşaretli hesaplar o oylamadan dışlanır; içerikleri silinmez.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction

from mesveret.domain.regulation import Regulation


@dataclass(frozen=True)
class RaidCluster:
    members: frozenset[str]
    density: Fraction
    span: timedelta
    reason: str


def _components(nodes: set[str], adj: dict[str, set[str]]) -> list[set[str]]:
    seen: set[str] = set()
    comps = []
    for start in sorted(nodes):
        if start in seen:
            continue
        comp = {start}
        stack = [start]
        seen.add(start)
        while stack:
            for nxt in adj.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    comp.add(nxt)
                    stack.append(nxt)
        comps.append(comp)
    return comps


def detect_raids(
    joined_at: Mapping[str, datetime],
    interactions: Mapping[tuple[str, str], float],
    at: datetime,
    reg: Regulation,
) -> list[RaidCluster]:
    window = reg.duration("baskin_yeni_uye_suresi")
    candidates = {u for u, t in joined_at.items() if at - window <= t <= at}
    if not candidates:
        return []

    undirected: dict[frozenset[str], float] = {}
    for (a, b), w in interactions.items():
        if a != b and a in candidates and b in candidates:
            key = frozenset((a, b))
            undirected[key] = undirected.get(key, 0.0) + w

    min_weight = reg.number("baskin_min_agirlik")
    adj: dict[str, set[str]] = {}
    edges = set()
    for pair, w in undirected.items():
        if w >= min_weight:
            a, b = tuple(pair)
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
            edges.add(pair)

    min_size = reg.integer("baskin_min_kume")
    density_ratio = reg.ratio("baskin_yogunluk_esigi")
    max_span = reg.duration("baskin_katilim_araligi")

    clusters = []
    for comp in _components(candidates, adj):
        n = len(comp)
        if n < min_size:
            continue
        possible = n * (n - 1) // 2
        inside = sum(1 for e in edges if e <= comp)
        times = [joined_at[u] for u in comp]
        span = max(times) - min(times)
        if not density_ratio.passes(inside, possible) or span > max_span:
            continue
        density = Fraction(inside, possible)
        hours = span.total_seconds() / 3600
        clusters.append(RaidCluster(
            frozenset(comp), density, span,
            f"{n} hesaplık yeni ve yoğun bağlantılı küme (yoğunluk %{float(density) * 100:.0f}, "
            f"katılım yayılımı {hours:.1f} saat): baskın şüphesi.",
        ))
    return clusters
