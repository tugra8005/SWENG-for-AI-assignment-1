"""Değerlendirme düzeneği (Facade): yapılandırmayı okur, depoyu ve tespitçileri kurar, her
tespitçiyi eğitir, aynı sınama kümesinde ölçer ve sonuçları gözlemcilere bildirir.

    uv run python -m mesveret.evaluation ../docs/degerlendirme/config.yaml

Ek analizler (rapordaki tablolar için):
- eşik taraması: üretim kuralında en küçük küme ve yoğunluk eşiği değişince kesinlik, duyarlılık
  ve maliyet;
- maliyet oranı taraması: hangi oranda hangi eşiğin en ucuz olduğu;
- yeni üyeler arasında ölçüm: eski üyeler kolay negatiftir ve doğruluğu şişirir;
- baskın biçimine göre duyarlılık ve gerçek grup türüne göre yanlış işaret oranı.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mesveret.evaluation.detectors import DETECTORS, ClusterDetector, Detector, evaluate
from mesveret.evaluation.metrics import Confusion, confusion, report
from mesveret.evaluation.observers import (
    ConsoleReporter,
    EvaluationObserver,
    JsonReporter,
)
from mesveret.evaluation.repository import (
    GeneratedScenarioRepository,
    JsonScenarioRepository,
    ScenarioRepository,
)
from mesveret.evaluation.scenarios import Scenario, generate


@dataclass
class Evaluation:
    config: dict[str, Any]
    repository: ScenarioRepository
    observers: list[EvaluationObserver] = field(default_factory=list)

    @property
    def costs(self) -> tuple[float, float]:
        m = self.config["maliyet"]
        return float(m["kacan"]), float(m["yanlis"])

    def detectors(self) -> list[tuple[str, Detector]]:
        """Fabrika: yapılandırmadaki her girdi için kayıt defterinden bir tespitçi."""
        c_fn, c_fp = self.costs
        out = []
        for entry in self.config["tespitciler"]:
            params = dict(entry.get("parametreler") or {})
            if entry["tur"] == "karar_agaci":
                params.setdefault("c_fn", c_fn)
                params.setdefault("c_fp", c_fp)
            out.append((entry.get("ad", entry["tur"]), DETECTORS.create(entry["tur"], **params)))
        return out

    def _notify(self, method: str, *args: Any) -> None:
        for o in self.observers:
            getattr(o, method)(*args)

    def run(self) -> dict[str, Any]:
        c_fn, c_fp = self.costs
        train, test = self.repository.load("egitim"), self.repository.load("sinama")
        self._notify("on_start", self.config)
        results: dict[str, Any] = {}
        for name, det in self.detectors():
            det.fit(train)
            m = report(evaluate(det, test), c_fn=c_fn, c_fp=c_fp)
            results[name] = m
            self._notify("on_result", name, "sinama", m, det.explain())
            newcomers = report(evaluate_newcomers(det, test), c_fn=c_fn, c_fp=c_fp)
            self._notify("on_result", name, "yeni", newcomers, det.explain())
        extras = {
            "veri": describe(train, test),
            "esik_taramasi": threshold_sweep(test, c_fn, c_fp),
            "maliyet_orani": cost_ratio_sweep(test),
            "bicime_gore": by_group(test, self.config),
            "sinif_payi": class_share_sweep(self.config),
        }
        for key, value in extras.items():
            self._notify("on_extra", key, value)
        self._notify("on_finish")
        return {"sonuclar": results, **extras}


# --- ek analizler -----------------------------------------------------------------------------


def evaluate_newcomers(det: Detector, scenarios: list[Scenario]) -> Confusion:
    """Yalnızca son yedi günde katılanlar arasında (eski üyeler paydadan çıkar)."""
    total = Confusion()
    for s in scenarios:
        pop = s.newcomers()
        total = total + confusion(det.predict(s) & pop, set(s.raiders) & pop, pop)
    return total


def describe(train: list[Scenario], test: list[Scenario]) -> dict[str, Any]:
    def stats(ss: list[Scenario]) -> dict[str, Any]:
        groups = Counter(g for s in ss for g in s.groups.values())
        return {"senaryo": len(ss), "hesap": sum(len(s.joined) for s in ss),
                "baskinci": sum(len(s.raiders) for s in ss),
                "baskinli_senaryo": sum(1 for s in ss if s.raiders),
                "yeni_uye": sum(len(s.newcomers()) for s in ss),
                "gruplar": dict(sorted(groups.items()))}

    return {"egitim": stats(train), "sinama": stats(test)}


def threshold_sweep(test: list[Scenario], c_fn: float, c_fp: float) -> list[dict[str, Any]]:
    """Üretim kuralında iki eşiğin taraması (diğerleri varsayılan)."""
    rows = []
    for kume in (3, 4, 5, 6, 8):
        for yogunluk in ("1/3", "1/2", "2/3", "1"):
            det = ClusterDetector(kume=kume, yogunluk=yogunluk)
            m = report(evaluate(det, test), c_fn=c_fn, c_fp=c_fp)
            rows.append({"kume": kume, "yogunluk": yogunluk, **m})
    return rows


def cost_ratio_sweep(test: list[Scenario]) -> list[dict[str, Any]]:
    """Yanlış işaretin kaçan baskıncıya göre bedeli r olduğunda en ucuz eşik birleşimi."""
    grid = [(k, y, evaluate(ClusterDetector(kume=k, yogunluk=y), test))
            for k in (3, 4, 5, 6, 8) for y in ("1/3", "1/2", "2/3", "1")]
    out = []
    for r in (0.2, 1, 5, 20):
        k, y, c = min(grid, key=lambda g: (g[2].cost(1, r), g[0], g[1]))
        out.append({"oran": r, "kume": k, "yogunluk": y, "maliyet": round(c.cost(1, r), 2),
                    "yn": c.fn, "yp": c.fp})
    return out


def by_group(test: list[Scenario], config: dict[str, Any]) -> dict[str, Any]:
    """Üretim kuralının (yapılandırmadaki ``kume`` girdisi) baskın biçimine göre duyarlılığı ve
    gerçek grup türüne göre yanlış işaret oranı."""
    entry = next((e for e in config["tespitciler"] if e["tur"] == "kume"), {"parametreler": {}})
    det = ClusterDetector(**(entry.get("parametreler") or {}))
    caught: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    for s in test:
        flagged = det.predict(s)
        for u, g in s.groups.items():
            if g == "eski":
                continue
            seen[g] += 1
            if u in flagged:
                caught[g] += 1
    return {g: {"hesap": seen[g], "isaretlenen": caught[g],
                "oran": round(caught[g] / seen[g], 3) if seen[g] else 0.0}
            for g in sorted(seen)}


def class_share_sweep(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Sonucun benzetim varsayımına duyarlılığı: birlikte kaydolan gerçek grupların (sınıf)
    payı değişince üretim kuralının kazancı. Kural "hiç kimseyi işaretleme"den ancak yanlış
    işaretin bedeli kaçan baskıncınınkinin ``dp / yp`` katından azsa ucuzdur (başa baş oranı)."""
    data = config["veri"]
    entry = next((e for e in config["tespitciler"] if e["tur"] == "kume"), {"parametreler": {}})
    det = ClusterDetector(**(entry.get("parametreler") or {}))
    out = []
    for share in (0.0, 0.1, 0.2, 0.35, 0.5):
        scenarios = generate(data["senaryo"] // 2, data["tohum"] + 1, class_share=share)
        c = evaluate(det, scenarios)
        out.append({"sinif_payi": share, "dp": c.tp, "yn": c.fn, "yp": c.fp,
                    "kesinlik": round(c.precision, 3), "duyarlilik": round(c.recall, 3),
                    "basabas_orani": round(c.tp / c.fp, 2) if c.fp else None})
    return out


# --- giriş noktası ------------------------------------------------------------------------------


def load_config(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def from_config(path: str | Path, *, quiet: bool = False) -> Evaluation:
    path = Path(path)
    config = load_config(path)
    data = config["veri"]
    generated = GeneratedScenarioRepository(data["senaryo"], data["tohum"], data["sinama_payi"])
    test_file = path.parent / data["sinama_dosyasi"]
    if not test_file.exists():
        JsonScenarioRepository.freeze(test_file, generated.load("sinama"))
    repo = JsonScenarioRepository(test_file, fallback=generated)
    observers: list[EvaluationObserver] = [] if quiet else [ConsoleReporter()]
    observers.append(JsonReporter(path.parent / config["cikti"]))
    return Evaluation(config, repo, observers)
