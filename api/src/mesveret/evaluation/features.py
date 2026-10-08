"""Hesap başına öznitelikler (öğrenen temel çizgi için).

Öznitelik çıkarımı öğrenen tespitçinin içindedir (Transform deseni): eğitimde ve sınamada aynı
kod çalışır, eğitim–sunum farkı (training–serving skew) oluşmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from mesveret.evaluation.scenarios import Scenario

WINDOW = timedelta(days=7)
EDGE_MIN = 1.0
FEATURES = ("yas_saat", "yeni_komsu_agirligi", "kume_boyutu", "kume_yogunlugu",
            "kume_yayilimi_saat", "eski_agirligi")
LABELS = {
    "yas_saat": "üyelik yaşı (saat)",
    "yeni_komsu_agirligi": "yeni üyelerle etkileşim ağırlığı",
    "kume_boyutu": "yeni üyeler arasındaki kümenin boyutu",
    "kume_yogunlugu": "kümenin kenar yoğunluğu",
    "kume_yayilimi_saat": "kümede katılım yayılımı (saat)",
    "eski_agirligi": "eski üyelerle etkileşim ağırlığı",
}


@dataclass(frozen=True)
class Row:
    account: str
    values: dict[str, float]
    raider: bool


def _undirected(s: Scenario) -> dict[frozenset[str], float]:
    out: dict[frozenset[str], float] = {}
    for (a, b), w in s.interactions.items():
        if a != b:
            key = frozenset((a, b))
            out[key] = out.get(key, 0.0) + w
    return out


def extract(s: Scenario) -> list[Row]:
    new = s.newcomers(WINDOW)
    und = _undirected(s)
    adj: dict[str, set[str]] = {u: set() for u in new}
    for pair, w in und.items():
        if w >= EDGE_MIN and pair <= new:
            a, b = tuple(pair)
            adj[a].add(b)
            adj[b].add(a)
    comp_of: dict[str, frozenset[str]] = {}
    for start in sorted(new):
        if start in comp_of:
            continue
        comp, stack = {start}, [start]
        while stack:
            for nxt in adj[stack.pop()]:
                if nxt not in comp:
                    comp.add(nxt)
                    stack.append(nxt)
        frozen = frozenset(comp)
        for u in comp:
            comp_of[u] = frozen
    rows = []
    for u, joined in sorted(s.joined.items()):
        age = (s.at - joined).total_seconds() / 3600
        if u not in new:
            values = {"yas_saat": min(age, 24 * 30), "yeni_komsu_agirligi": 0.0, "kume_boyutu": 0,
                      "kume_yogunlugu": 0.0, "kume_yayilimi_saat": 0.0, "eski_agirligi": 0.0}
            rows.append(Row(u, values, u in s.raiders))
            continue
        comp = comp_of[u]
        n = len(comp)
        edges = sum(1 for pair in und if pair <= comp and und[pair] >= EDGE_MIN) if n > 1 else 0
        times = [s.joined[v] for v in comp]
        values = {
            "yas_saat": age,
            "yeni_komsu_agirligi": sum(w for pair, w in und.items() if u in pair and pair <= new),
            "kume_boyutu": n,
            "kume_yogunlugu": edges / (n * (n - 1) / 2) if n > 1 else 0.0,
            "kume_yayilimi_saat": (max(times) - min(times)).total_seconds() / 3600,
            "eski_agirligi": sum(w for pair, w in und.items() if u in pair and not pair <= new),
        }
        rows.append(Row(u, values, u in s.raiders))
    return rows
