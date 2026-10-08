"""Değerlendirme gözlemcileri (Observer deseni).

Düzenek sonuçları üretir; nereye yazılacaklarını bilmez. Konsol tablosu ve JSON dosyası birer
gözlemcidir; yenisi (ör. bir deney izleme sunucusu) düzeneği değiştirmeden eklenir.
"""

from __future__ import annotations

import json
import sys
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
