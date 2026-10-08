"""Değerlendirme düzeneğinin bileşen testleri (sahte depo ve sahte gözlemciyle)."""

import json
from datetime import timedelta

import pytest

from mesveret.domain.raid import detect_raids
from mesveret.domain.regulation import Regulation
from mesveret.evaluation import features
from mesveret.evaluation.detectors import DETECTORS, evaluate
from mesveret.evaluation.harness import Evaluation
from mesveret.evaluation.metrics import Confusion, confusion, report
from mesveret.evaluation.observers import EvaluationObserver, JsonReporter
from mesveret.evaluation.repository import (
    GeneratedScenarioRepository,
    InMemoryScenarioRepository,
    JsonScenarioRepository,
)
from mesveret.evaluation.scenarios import Scenario, T, generate, split_of


def _raid_scenario(name="baskin") -> Scenario:
    """30 eski üye ve dakikalar arayla kaydolup birbirine yanıt veren 5 hesap."""
    joined = {f"eski{i}": T - timedelta(days=100 + i) for i in range(30)}
    raiders = [f"b{i}" for i in range(5)]
    joined |= {u: T - timedelta(hours=3, minutes=-8 * i) for i, u in enumerate(raiders)}
    inter = {(a, b): 1.0 for a in raiders for b in raiders if a != b}
    return Scenario(name, T, joined, inter, frozenset(raiders))


def _quiet_scenario(name="sakin") -> Scenario:
    joined = {f"eski{i}": T - timedelta(days=100 + i) for i in range(30)}
    joined["yeni"] = T - timedelta(days=2)
    return Scenario(name, T, joined, {("yeni", "eski0"): 1.0})


# --- metrikler ----------------------------------------------------------------------------------


def test_metrics_match_the_lecture_example():
    # Problem çerçeveleme, slayt 26–31: 1000 mesaj, 50 acil; DP 40, YN 10, YP 60, DN 890.
    c = Confusion(tp=40, fn=10, fp=60, tn=890)
    assert c.accuracy == pytest.approx(0.93)
    assert (c.precision, c.recall) == (pytest.approx(0.40), pytest.approx(0.80))
    assert c.f1 == pytest.approx(0.533, abs=1e-3)
    assert c.f_beta(2) == pytest.approx(0.667, abs=1e-3)
    assert c.f_beta(0.5) == pytest.approx(0.444, abs=1e-3)
    assert c.cost(c_fn=100, c_fp=5) == 1300
    # "hep acil değil": %95 doğruluk, sıfır duyarlılık
    lazy = Confusion(tp=0, fn=50, fp=0, tn=950)
    assert lazy.accuracy == pytest.approx(0.95) and lazy.recall == 0 and lazy.f1 == 0


def test_confusion_from_sets_and_report_keys():
    c = confusion({"a", "x"}, {"a", "b"}, {"a", "b", "x", "y"})
    assert (c.tp, c.fn, c.fp, c.tn) == (1, 1, 1, 1)
    assert report(c, c_fn=1, c_fp=5)["maliyet"] == 6


# --- senaryolar ve depolar ----------------------------------------------------------------------


def test_generation_is_deterministic_and_split_is_stable():
    a, b = generate(6, seed=7), generate(6, seed=7)
    assert [s.to_json() for s in a] == [s.to_json() for s in b]
    assert [split_of(s.name) for s in a] == [split_of(s.name) for s in b]
    s = a[0]
    assert Scenario.from_json(json.loads(json.dumps(s.to_json()))).to_json() == s.to_json()
    assert all(t <= s.at for t in s.joined.values())  # gelecekte katılan yok


def test_repositories_share_one_interface(tmp_path):
    raid, quiet = _raid_scenario(), _quiet_scenario()
    mem = InMemoryScenarioRepository([quiet], [raid])
    assert [s.name for s in mem.load("sinama")] == ["baskin"]
    path = tmp_path / "sinama.json"
    JsonScenarioRepository.freeze(path, [raid])
    repo = JsonScenarioRepository(path, fallback=mem)
    assert repo.load("sinama")[0].raiders == raid.raiders
    assert [s.name for s in repo.load("egitim")] == ["sakin"]  # dosyada yok: yedek depodan
    gen = GeneratedScenarioRepository(20, seed=3)
    names = {s.name for s in gen.load("egitim")} | {s.name for s in gen.load("sinama")}
    assert len(names) == 20 and not {s.name for s in gen.load("egitim")} & {
        s.name for s in gen.load("sinama")}


# --- öznitelikler ve tespitçiler ----------------------------------------------------------------


def test_features_describe_the_raid_cluster():
    rows = {r.account: r for r in features.extract(_raid_scenario())}
    b0 = rows["b0"].values
    assert b0["kume_boyutu"] == 5 and b0["kume_yogunlugu"] == 1.0
    assert b0["kume_yayilimi_saat"] == pytest.approx(32 / 60)
    assert rows["eski0"].values["kume_boyutu"] == 0 and not rows["eski0"].raider


def test_registry_knows_the_baseline_ladder():
    assert set(DETECTORS) == {"rastgele", "hic_kimse", "yeni_uye", "kume", "karar_agaci"}
    raid = _raid_scenario()
    assert DETECTORS.create("hic_kimse").predict(raid) == set()
    assert DETECTORS.create("yeni_uye", gun=7).predict(raid) == set(raid.raiders)
    cluster = DETECTORS.create("kume").predict(raid)
    production = {u for c in detect_raids(raid.joined, raid.interactions, raid.at,
                                          Regulation.defaults()) for u in c.members}
    assert cluster == production == set(raid.raiders)  # aynı kod: eğitim–sunum farkı yok
    assert DETECTORS.create("kume", kume=6).predict(raid) == set()
    rnd = DETECTORS.create("rastgele", seed=1).fit([raid])
    assert rnd.predict(raid) == rnd.predict(raid)


def test_decision_tree_learns_a_rule_and_explains_it():
    train = [_raid_scenario(f"b{i}") for i in range(3)] + [_quiet_scenario(f"q{i}") for i in range(3)]
    tree = DETECTORS.create("karar_agaci", c_fn=1, c_fp=5).fit(train)
    raid = _raid_scenario("sinama")
    assert tree.predict(raid) == set(raid.raiders)
    assert tree.predict(_quiet_scenario("q")) == set()
    assert tree.explain().startswith("İşaretle:")


# --- gözlemciler ve düzenek (Facade) -------------------------------------------------------------


class _Recorder(EvaluationObserver):
    def __init__(self):
        self.calls = []

    def on_start(self, config):
        self.calls.append("start")

    def on_result(self, name, split, metrics, explanation):
        self.calls.append(f"{name}:{split}")

    def on_extra(self, key, value):
        self.calls.append(f"ek:{key}")

    def on_finish(self):
        self.calls.append("finish")


CONFIG = {
    "veri": {"senaryo": 10, "tohum": 1, "sinama_payi": 0.3},
    "maliyet": {"kacan": 1, "yanlis": 5},
    "tespitciler": [{"tur": "hic_kimse"}, {"tur": "kume"}, {"tur": "karar_agaci"}],
}


def test_evaluation_facade_notifies_observers_and_passes_costs(tmp_path):
    rec, js = _Recorder(), JsonReporter(tmp_path / "out.json")
    repo = InMemoryScenarioRepository([_raid_scenario("e1"), _quiet_scenario("e2")],
                                      [_raid_scenario("s1"), _quiet_scenario("s2")])
    ev = Evaluation(CONFIG, repo, [rec, js])
    tree = dict(ev.detectors())["karar_agaci"]
    assert (tree.c_fn, tree.c_fp) == (1.0, 5.0)  # maliyet yapılandırmadan
    out = ev.run()
    assert rec.calls[0] == "start" and rec.calls[-1] == "finish"
    assert "kume:sinama" in rec.calls and "ek:esik_taramasi" in rec.calls
    assert out["sonuclar"]["kume"]["duyarlilik"] == 1.0
    assert out["sonuclar"]["hic_kimse"]["maliyet"] == 5  # 5 kaçan baskıncı × 1
    saved = json.loads((tmp_path / "out.json").read_text())
    assert {r["tespitci"] for r in saved["sonuclar"]} == {"hic_kimse", "kume", "karar_agaci"}
    assert evaluate(dict(ev.detectors())["kume"], [_quiet_scenario()]).fp == 0
