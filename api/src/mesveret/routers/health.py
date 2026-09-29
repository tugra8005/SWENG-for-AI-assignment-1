import httpx
from fastapi import APIRouter, Request
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
def health(request: Request) -> dict:
    def pg() -> None:
        with get_sessionmaker()() as s:
            s.execute(text("SELECT 1"))

    def neo() -> None:
        get_driver().verify_connectivity()

    in_memory = not hasattr(request.app.state.graph, "ensure_constraints")

    ledger = {}
    for url in get_settings().ledger_nodes:
        ledger[url] = _check(lambda url=url: httpx.get(f"{url}/health", timeout=2).raise_for_status())

    graph_status = "bellek içi (Docker'sız geliştirme modu)" if in_memory else _check(neo)
    parts = {"postgres": _check(pg), "neo4j": graph_status, "defter": ledger}
    all_ok = parts["postgres"] == "ok" and (in_memory or parts["neo4j"] == "ok") and all(
        v == "ok" for v in ledger.values()
    )
    # "ortam": istemci geliştirmeye özgü notları (ör. doğrulama kodu konsolda) yalnızca dev'de gösterir.
    return {"durum": "ok" if all_ok else "eksik", "ortam": get_settings().env, **parts}
