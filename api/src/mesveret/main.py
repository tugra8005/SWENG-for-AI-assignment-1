from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mesveret.config import Settings, get_settings
from mesveret.errors import DomainError
from mesveret.routers import auth, health, ontology, proposals, topics, users


def default_graph(settings: Settings):
    if settings.graph_backend == "memory":
        from mesveret.graph.memory import InMemoryGraph

        return InMemoryGraph()
    from mesveret.graph.driver import get_driver
    from mesveret.graph.neo4j_store import Neo4jGraph

    return Neo4jGraph(get_driver())


def default_ledger(settings: Settings):
    from mesveret.services.ledger import FakeLedgerClient, HttpLedgerClient

    if settings.ledger_backend == "fake":
        return FakeLedgerClient()
    return HttpLedgerClient(settings.ledger_leader_url, settings.ledger_nodes, settings.ledger_token)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from mesveret.db.base import create_schema
    from mesveret.graph.driver import close_driver
    from mesveret.services import scheduler

    logging.basicConfig(level=logging.INFO)
    create_schema()
    if hasattr(app.state.graph, "ensure_constraints"):
        app.state.graph.ensure_constraints()
    stop = None
    if app.state.settings.scheduler_enabled:
        stop = scheduler.start_background(app.state)
    yield
    if stop is not None:
        stop.set()
    close_driver()


def create_app(
    *,
    settings: Settings | None = None,
    graph: Any = None,
    ledger: Any = None,
    sessionmaker: Any = None,
    with_lifespan: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Meşveret API", version="0.1.0", lifespan=lifespan if with_lifespan else None
    )
    app.state.settings = settings
    app.state.graph = graph if graph is not None else default_graph(settings)
    app.state.ledger = ledger if ledger is not None else default_ledger(settings)
    if sessionmaker is None:
        from mesveret.db.base import get_sessionmaker

        sessionmaker = get_sessionmaker()
    app.state.sessionmaker = sessionmaker

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"detail": exc.message, "violations": exc.violations}
        )

    for module in (health, auth, users, ontology, topics, proposals):
        app.include_router(module.router)
    return app


def app_from_env() -> FastAPI:
    """``uvicorn --factory mesveret.main:app_from_env``"""
    return create_app()
