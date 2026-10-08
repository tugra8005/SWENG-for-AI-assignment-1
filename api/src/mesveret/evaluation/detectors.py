"""Baskın tespitçileri (Strategy) ve kayıt defteri (Registry + Factory).

Her tespitçi aynı arayüzü sunar: ``fit(eğitim senaryoları)`` ve ``predict(senaryo) -> işaretli
hesaplar``. Temel çizgi merdiveni basamak basamak:

1. ``rastgele``: eğitimdeki baskıncı oranıyla rastgele işaretler.
2. ``hic_kimse``: hiç kimseyi işaretlemez (çoğunluk sınıfı).
3. ``yeni_uye``: son N günde katılan herkesi işaretler (basit kural).
4. ``kume``: üretimdeki kural (``domain.raid.detect_raids``), yönetmelik eşikleriyle.
5. ``karar_agaci``: hesap başına özniteliklerden maliyete göre öğrenilmiş derinliği 2 ağaç.

Hangi tespitçilerin hangi parametrelerle çalışacağı yapılandırma dosyasındadır; kod somut sınıf
adlarını görmez: ``DETECTORS.create(ad, **parametreler)``.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from mesveret.domain.raid import detect_raids
from mesveret.domain.registry import Registry
from mesveret.domain.regulation import Regulation
from mesveret.evaluation import features
from mesveret.evaluation.metrics import Confusion
from mesveret.evaluation.scenarios import Scenario


class Detector(ABC):
    name: str = ""
    description: str = ""

    def fit(self, train: list[Scenario]) -> Detector:
        """Kural tabanlı tespitçiler öğrenmez; varsayılan hiçbir şey yapmaz."""
        return self

    @abstractmethod
    def predict(self, s: Scenario) -> set[str]: ...

    def explain(self) -> str:
        return self.description


DETECTORS = Registry[Detector]("baskın tespitçisi")


@DETECTORS.register("rastgele")
class RandomDetector(Detector):
    description = "Her hesabı eğitimdeki baskıncı oranıyla rastgele işaretler."

    def __init__(self, seed: int = 42) -> None:
        self.seed, self.rate = seed, 0.0

    def fit(self, train: list[Scenario]) -> Detector:
        accounts = sum(len(s.joined) for s in train)
        self.rate = sum(len(s.raiders) for s in train) / accounts if accounts else 0.0
        return self

    def predict(self, s: Scenario) -> set[str]:
        rng = random.Random(f"{self.seed}:{s.name}")
        return {u for u in sorted(s.joined) if rng.random() < self.rate}

    def explain(self) -> str:
        return f"Her hesabı %{self.rate * 100:.2f} olasılıkla işaretler (eğitimdeki oran)."


@DETECTORS.register("hic_kimse")
class NobodyDetector(Detector):
    description = "Hiç kimseyi işaretlemez (çoğunluk sınıfı: 'baskın yok')."

    def predict(self, s: Scenario) -> set[str]:
        return set()


@DETECTORS.register("yeni_uye")
class NewMemberRule(Detector):
    def __init__(self, gun: float = 7) -> None:
        self.window = timedelta(days=gun)
        self.description = f"Son {gun:g} günde katılan her hesabı işaretler."

    def predict(self, s: Scenario) -> set[str]:
        return s.newcomers(self.window)


def regulation_with(*, kume: int | None = None, yogunluk: str | None = None,
                    agirlik: float | None = None, gun: float | None = None,
                    saat: float | None = None) -> Regulation:
    """Varsayılan yönetmelik, baskın eşikleri verilenlerle değiştirilmiş olarak."""
    values = {k: dict(v) for k, v in Regulation.defaults().values.items()}
    if kume is not None:
        values["baskin_min_kume"] = {"deger": kume}
    if yogunluk is not None:
        values["baskin_yogunluk_esigi"] = {"karsilastirma": ">=", "oran": yogunluk}
    if agirlik is not None:
        values["baskin_min_agirlik"] = {"deger": agirlik}
    if gun is not None:
        values["baskin_yeni_uye_suresi"] = {"gun": gun}
    if saat is not None:
        values["baskin_katilim_araligi"] = {"saat": saat}
    return Regulation(values)


@DETECTORS.register("kume")
class ClusterDetector(Detector):
    """Üretimdeki tespit: aynı fonksiyon, yalnızca eşikler yapılandırmadan."""

    def __init__(self, **thresholds: Any) -> None:
        self.thresholds = thresholds
        self.reg = regulation_with(**thresholds)
        r = self.reg
        self.description = (
            f"Son {r.raw('baskin_yeni_uye_suresi')['gun']} günde katılanlar arasında, en az "
            f"{r.integer('baskin_min_kume')} hesaplık, yoğunluğu ≥ "
            f"{r.raw('baskin_yogunluk_esigi')['oran']}, katılım yayılımı ≤ "
            f"{r.raw('baskin_katilim_araligi')['saat']} saat olan küme (kenar ağırlığı ≥ "
            f"{r.number('baskin_min_agirlik')}).")

    def predict(self, s: Scenario) -> set[str]:
        return {u for c in detect_raids(s.joined, s.interactions, s.at, self.reg)
                for u in c.members}


@dataclass(frozen=True)
class _Split:
    feature: str
    threshold: float

    def goes_right(self, row: features.Row) -> bool:
        return row.values[self.feature] >= self.threshold


def _leaf_cost(rows: list[features.Row], c_fn: float, c_fp: float) -> tuple[float, bool]:
    """Yaprağın en ucuz kararı: hepsini işaretle (maliyet c_fp·gerçek) ya da hiçbirini
    (maliyet c_fn·baskıncı)."""
    raiders = sum(1 for r in rows if r.raider)
    flag_cost, keep_cost = c_fp * (len(rows) - raiders), c_fn * raiders
    return (flag_cost, True) if flag_cost < keep_cost else (keep_cost, False)


def _best_split(rows: list[features.Row], c_fn: float, c_fp: float,
                names: tuple[str, ...]) -> tuple[float, _Split | None]:
    """Maliyeti en çok düşüren (öznitelik, eşik). Her öznitelik için satırlar sıralanıp bir kez
    taranır (O(n log n)); eşik iki ardışık farklı değerin ortasıdır."""
    best_cost, best = _leaf_cost(rows, c_fn, c_fp)[0], None
    total_r = sum(1 for r in rows if r.raider)
    total_l = len(rows) - total_r
    for name in names:
        ordered = sorted(rows, key=lambda r: r.values[name])
        left_r = left_l = 0
        for i in range(len(ordered) - 1):
            if ordered[i].raider:
                left_r += 1
            else:
                left_l += 1
            lo, hi = ordered[i].values[name], ordered[i + 1].values[name]
            if lo == hi:
                continue
            cost = (min(c_fp * left_l, c_fn * left_r)
                    + min(c_fp * (total_l - left_l), c_fn * (total_r - left_r)))
            if cost < best_cost - 1e-9:
                best_cost, best = cost, _Split(name, (lo + hi) / 2)
    return best_cost, best


@DETECTORS.register("karar_agaci")
class DecisionTreeDetector(Detector):
    """Derinliği 2 karar ağacı: her düğümde, hata maliyetini en çok düşüren öznitelik ve eşik.
    Öznitelik çıkarımı nesnenin içindedir (eğitimde ve tahminde aynı kod)."""

    def __init__(self, c_fn: float = 1.0, c_fp: float = 1.0,
                 features_used: list[str] | None = None) -> None:
        self.c_fn, self.c_fp = c_fn, c_fp
        self.names = tuple(features_used or features.FEATURES)
        self.root: _Split | None = None
        self.children: dict[bool, tuple[_Split | None, dict[bool, bool]]] = {}
        self.leaf = False

    def fit(self, train: list[Scenario]) -> Detector:
        rows = [r for s in train for r in features.extract(s)]
        _, self.root = _best_split(rows, self.c_fn, self.c_fp, self.names)
        if self.root is None:
            self.leaf = _leaf_cost(rows, self.c_fn, self.c_fp)[1]
            return self
        for side in (False, True):
            part = [r for r in rows if self.root.goes_right(r) is side]
            _, child = _best_split(part, self.c_fn, self.c_fp, self.names)
            if child is None:
                self.children[side] = (None, {False: _leaf_cost(part, self.c_fn, self.c_fp)[1]})
            else:
                leaves = {s: _leaf_cost([r for r in part if child.goes_right(r) is s],
                                        self.c_fn, self.c_fp)[1] for s in (False, True)}
                self.children[side] = (child, leaves)
        return self

    def _decide(self, row: features.Row) -> bool:
        if self.root is None:
            return self.leaf
        child, leaves = self.children[self.root.goes_right(row)]
        if child is None:
            return leaves[False]
        return leaves[child.goes_right(row)]

    def predict(self, s: Scenario) -> set[str]:
        return {r.account for r in features.extract(s) if self._decide(r)}

    def explain(self) -> str:
        if self.root is None:
            return "Ağaç bölünmedi: herkes için tek karar."

        def cond(split: _Split, right: bool) -> str:
            op = "≥" if right else "<"
            return f"{features.LABELS[split.feature]} {op} {split.threshold:.2f}"

        rules = []
        for side in (False, True):
            child, leaves = self.children[side]
            if child is None:
                if leaves[False]:
                    rules.append(cond(self.root, side))
                continue
            for s in (False, True):
                if leaves[s]:
                    rules.append(f"{cond(self.root, side)} ve {cond(child, s)}")
        return ("İşaretle: " + "; ya da ".join(rules) + ".") if rules else "Kimseyi işaretleme."


def evaluate(detector: Detector, scenarios: list[Scenario]) -> Confusion:
    from mesveret.evaluation.metrics import confusion

    total = Confusion()
    for s in scenarios:
        total = total + confusion(detector.predict(s), set(s.raiders), s.accounts)
    return total
