"""Rapor diyagramları için kodun yapısını dışa aktarır (``sema.json``).

    uv run --directory api python ../docs/rapor/sema.py

- PostgreSQL tabloları: sütunlar, birincil ve yabancı anahtarlar, boş olabilirlik, tekil kısıtlar
  (SQLAlchemy metadata'sından).
- Paket bağımlılıkları: ``mesveret`` alt paketleri arasındaki içe aktarmalar (kaynak koddan).
- Tasarım sınıfları: sınıfların ataları, soyut işlemleri ve kendi tanımladığı işlemler.

Rapor betiği (``olustur.py``) bu dosyayı okur; böylece raporu üretmek için API'nin bağımlılıkları
gerekmez, diyagramlar da koddan sapmaz.
"""

from __future__ import annotations

import collections
import dataclasses
import importlib
import inspect
import json
import re
from pathlib import Path

from mesveret.db import models  # noqa: F401  (tabloları kaydeder)
from mesveret.db.base import Base

OUT = Path(__file__).resolve().parent / "sema.json"
SRC = Path(importlib.import_module("mesveret").__file__).resolve().parent

CLASS_MODULES = [
    "mesveret.services.proposal_kinds", "mesveret.domain.lifecycle", "mesveret.domain.rules",
    "mesveret.services.decision_hour", "mesveret.services.jobs", "mesveret.services.events",
    "mesveret.domain.registry", "mesveret.evaluation.detectors", "mesveret.evaluation.repository",
    "mesveret.evaluation.observers", "mesveret.evaluation.harness", "mesveret.evaluation.metrics",
    "mesveret.evaluation.scenarios", "mesveret.services.ledger", "mesveret.domain.ontology",
    "mesveret.graph.store", "mesveret.graph.memory", "mesveret.graph.neo4j_store", "mesveret.context",
]


def tables() -> dict:
    out = {}
    for t in Base.metadata.sorted_tables:
        cols = []
        for c in t.columns:
            cols.append({
                "name": c.name, "type": type(c.type).__name__, "pk": bool(c.primary_key),
                "null": bool(c.nullable) and not c.primary_key,
                "fk": [f"{f.column.table.name}.{f.column.name}" for f in c.foreign_keys],
            })
        uniq = {tuple(col.name for col in con.columns) for con in t.constraints
                if con.__class__.__name__ == "UniqueConstraint"}
        uniq |= {(c.name,) for c in t.columns if c.unique}
        # Kısıtlar kümeden gelir; sıralanmazsa dosya her üretimde değişir.
        out[t.name] = {"columns": cols, "unique": [list(u) for u in sorted(uniq)]}
    return out


def packages() -> dict:
    deps: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    units = set()
    for f in SRC.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(SRC)
        unit = rel.parts[0].removesuffix(".py")
        if unit == "__init__":
            continue
        units.add(unit)
        for m in re.findall(r"^\s*(?:from|import)\s+mesveret\.([a-z_]+)", f.read_text("utf-8"), re.M):
            if m != unit:
                deps[unit][m] += 1
    return {"units": sorted(units), "deps": {u: dict(sorted(d.items())) for u, d in sorted(deps.items())}}


def classes() -> dict:
    out = {}
    for mn in CLASS_MODULES:
        m = importlib.import_module(mn)
        for name, cls in inspect.getmembers(m, inspect.isclass):
            if cls.__module__ != mn:
                continue
            own = [k for k, v in cls.__dict__.items()
                   if not k.startswith("__") and (inspect.isfunction(v) or isinstance(v, (staticmethod, classmethod, property)))]
            out[f"{mn}.{name}"] = {
                "name": name, "module": mn,
                "bases": [b.__name__ for b in cls.__bases__ if b is not object],
                "abstract": sorted(getattr(cls, "__abstractmethods__", [])),
                "methods": own,
                "fields": [f.name for f in dataclasses.fields(cls)] if dataclasses.is_dataclass(cls) else [],
            }
    return out


if __name__ == "__main__":
    OUT.write_text(json.dumps({"tables": tables(), "packages": packages(), "classes": classes()},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT} yazıldı")
