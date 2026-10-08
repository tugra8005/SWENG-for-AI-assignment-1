"""``python -m mesveret.evaluation <config.yaml> [--canli]``

``--canli``: canlı yığındaki ilk Karar Saati'nin anlık görüntüsünde de ölçer (veritabanı ister;
``docker compose exec -T api python -m mesveret.evaluation /app/degerlendirme/config.yaml --canli``).
"""

from __future__ import annotations

import sys

from mesveret.evaluation.detectors import evaluate
from mesveret.evaluation.harness import from_config
from mesveret.evaluation.metrics import report


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    evaluation = from_config(argv[0])
    if "--canli" in argv:
        from mesveret.cli import _ctx
        from mesveret.evaluation.observers import JsonReporter
        from mesveret.evaluation.repository import LiveScenarioRepository

        with _ctx() as ctx:
            live = LiveScenarioRepository(ctx).load("sinama")
        c_fn, c_fp = evaluation.costs
        train = evaluation.repository.load("egitim")
        rows = {}
        for name, det in evaluation.detectors():
            det.fit(train)
            rows[name] = report(evaluate(det, live), c_fn=c_fn, c_fp=c_fp)
        for o in evaluation.observers:
            if isinstance(o, JsonReporter):
                o.on_extra("canli", {"senaryo": [s.name for s in live],
                                     "secmen": sum(len(s.joined) for s in live),
                                     "baskinci": sum(len(s.raiders) for s in live),
                                     "sonuclar": rows})
    evaluation.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
