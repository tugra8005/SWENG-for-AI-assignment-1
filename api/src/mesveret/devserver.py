"""Docker'sız yerel geliştirme sunucusu.

Neo4j yerine bellek içi graf kullanır; PostgreSQL ve defter düğümleri ortam değişkenlerinden
okunur. Açılışta tohum veriyi baştan kurar (graf bellek içi olduğu için her açılışta).
CLI ayrı süreçte çalıştığından bellek içi grafa erişemez; zaman ve Karar Saati araçları bu
modda ``/_dev`` uç noktalarından sunulur. Asıl kurulum için docker compose kullanın.

    DATABASE_URL=... uv run python -m mesveret.devserver --port 8000
"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from mesveret import clock
from mesveret.config import get_settings
from mesveret.context import Ctx
from mesveret.db.base import get_sessionmaker
from mesveret.graph.memory import InMemoryGraph
from mesveret.main import create_app, default_ledger
from mesveret.routers import devtools
from mesveret.services import seed


def main() -> None:
    parser = argparse.ArgumentParser(description="Meşveret yerel geliştirme sunucusu")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    settings = get_settings()
    graph = InMemoryGraph()
    ledger = default_ledger(settings)
    db = get_sessionmaker()()
    ctx = Ctx(db=db, graph=graph, now=clock.real_now(), settings=settings, ledger=ledger)
    for line in seed.run(ctx, reset=True):
        print(line, flush=True)

    app = create_app(settings=settings, graph=graph, ledger=ledger)
    app.include_router(devtools.router)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
