import httpx
from fastapi import APIRouter
from sqlalchemy import text

from mesveret.config import get_settings
from mesveret.db.base import get_sessionmaker
from mesveret.graph.driver import get_driver

router = APIRouter(tags=["sağlık"])


def _check(fn) -> str:
    try:
        fn()
        return "ok"
    except Exception as exc:  # noqa: BLE001  (sağlık raporu her hatayı yakalar)
        return f"hata: {type(exc).__name__}"


@router.get("/health")
def health() -> dict:
    def pg() -> None:
        with get_sessionmaker()() as s:
            s.execute(text("SELECT 1"))

    def neo() -> None:
        get_driver().verify_connectivity()

    ledger = {}
    for url in get_settings().ledger_nodes:
        ledger[url] = _check(lambda url=url: httpx.get(f"{url}/health", timeout=2).raise_for_status())

    parts = {"postgres": _check(pg), "neo4j": _check(neo), "defter": ledger}
    all_ok = parts["postgres"] == "ok" and parts["neo4j"] == "ok" and all(
        v == "ok" for v in ledger.values()
    )
    return {"durum": "ok" if all_ok else "eksik", **parts}
