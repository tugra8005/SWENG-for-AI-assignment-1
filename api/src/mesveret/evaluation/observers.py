"""Değerlendirme gözlemcileri (Observer deseni).

Düzenek sonuçları üretir; nereye yazılacaklarını bilmez. Konsol tablosu, JSON dosyası ve MLflow
deney kaydı birer gözlemcidir; yenisi düzeneği değiştirmeden eklenir.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, TextIO


class EvaluationObserver:
    def on_start(self, config: dict[str, Any]) -> None: ...

    def on_result(self, name: str, split: str, metrics: dict[str, Any], explanation: str) -> None:
        ...

    def on_extra(self, key: str, value: Any) -> None: ...

    def on_finish(self) -> None: ...


class ConsoleReporter(EvaluationObserver):
    COLUMNS = ("dp", "yn", "yp", "dogruluk", "kesinlik", "duyarlilik", "f1", "f2", "maliyet")

    def __init__(self, out: TextIO | None = None) -> None:
        self.out = out or sys.stdout

    def on_start(self, config: dict[str, Any]) -> None:
        print(f"Baskın tespiti değerlendirmesi · maliyet: kaçan baskıncı "
              f"{config['maliyet']['kacan']}, yanlış işaret {config['maliyet']['yanlis']}",
              file=self.out)
        print(f"{'tespitçi':<14}{'küme':<8}" + "".join(f"{c:>11}" for c in self.COLUMNS),
              file=self.out)

    def on_result(self, name: str, split: str, metrics: dict[str, Any], explanation: str) -> None:
        cells = "".join(f"{metrics[c]:>11}" for c in self.COLUMNS)
        print(f"{name:<14}{split:<8}{cells}", file=self.out)


class JsonReporter(EvaluationObserver):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"sonuclar": [], "ek": {}}

    def on_start(self, config: dict[str, Any]) -> None:
        self.data["yapilandirma"] = config

    def on_result(self, name: str, split: str, metrics: dict[str, Any], explanation: str) -> None:
        self.data["sonuclar"].append({"tespitci": name, "kume": split, "aciklama": explanation,
                                      **metrics})

    def on_extra(self, key: str, value: Any) -> None:
        self.data["ek"][key] = value

    def on_finish(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")


class MlflowReporter(EvaluationObserver):
    """Sonuçları MLflow'a yazar: her değerlendirme bir üst koşudur (yapılandırma parametre olarak,
    eşik ve oran taramaları ek dosya olarak), her tespitçi onun altında bir koşudur (sınama ve yeni
    üye kümelerindeki metrikler). MLflow arayüzünde tespitçiler yan yana karşılaştırılır.

    Depo yereldir, sunucu gerekmez (MLflow 3.7'den beri varsayılan SQLite):
        uv run mlflow ui --backend-store-uri sqlite:///../docs/degerlendirme/mlflow.db

    MLflow yalnızca geliştirme bağımlılığıdır (``dev`` grubu); API imajında yoktur. Bu yüzden içe
    aktarma burada, sınıf kurulurken yapılır.
    """

    def __init__(self, tracking_uri: str, experiment: str, *, artifact_dir: str | Path | None = None,
                 run_name: str = "degerlendirme") -> None:
        from mlflow.tracking import MlflowClient

        self.client = MlflowClient(tracking_uri=tracking_uri)
        found = self.client.get_experiment_by_name(experiment)
        if found is not None:
            self.experiment_id = found.experiment_id
        else:
            location = Path(artifact_dir).resolve().as_uri() if artifact_dir else None
            self.experiment_id = self.client.create_experiment(experiment, artifact_location=location)
        self.run_name = run_name
        self.parent: str | None = None
        self.children: dict[str, str] = {}

    @staticmethod
    def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                MlflowReporter._flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
        elif isinstance(value, list):
            out[prefix] = json.dumps(value, ensure_ascii=False)
        else:
            out[prefix] = str(value)

    def on_start(self, config: dict[str, Any]) -> None:
        from mlflow.entities import Param

        run = self.client.create_run(self.experiment_id, run_name=self.run_name,
                                     tags={"bilesen": "baskin_tespiti"})
        self.parent = run.info.run_id
        params: dict[str, str] = {}
        self._flatten("", {k: v for k, v in config.items() if k != "mlflow"}, params)
        self.client.log_batch(self.parent, params=[Param(k, v) for k, v in sorted(params.items())])

    def _child(self, name: str) -> str:
        if name not in self.children:
            run = self.client.create_run(self.experiment_id, run_name=name,
                                         tags={"mlflow.parentRunId": self.parent, "tespitci": name})
            self.children[name] = run.info.run_id
        return self.children[name]

    def on_result(self, name: str, split: str, metrics: dict[str, Any], explanation: str) -> None:
        from mlflow.entities import Metric

        run_id = self._child(name)
        now = int(time.time() * 1000)
        values = [Metric(f"{split}.{k}", float(v), now, 0) for k, v in metrics.items()
                  if isinstance(v, (int, float)) and not isinstance(v, bool)]
        self.client.log_batch(run_id, metrics=values)
        if explanation:
            self.client.set_tag(run_id, "aciklama", explanation[:5000])

    def on_extra(self, key: str, value: Any) -> None:
        if self.parent is not None:
            self.client.log_dict(self.parent, value, f"ek/{key}.json")

    def on_finish(self) -> None:
        for run_id in self.children.values():
            self.client.set_terminated(run_id)
        if self.parent is not None:
            self.client.set_terminated(self.parent)
