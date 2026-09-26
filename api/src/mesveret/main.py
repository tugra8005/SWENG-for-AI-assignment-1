from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mesveret.config import get_settings
from mesveret.db.base import create_schema
from mesveret.graph.driver import close_driver
from mesveret.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_schema()
    yield
    close_driver()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Meşveret API",
        version="0.1.0",
        lifespan=lifespan if with_lifespan else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
