from functools import lru_cache
from typing import Any

from neo4j import Driver, GraphDatabase, Query

from mesveret.config import get_settings


@lru_cache
def get_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(
        s.neo4j_url,
        auth=(s.neo4j_user, s.neo4j_password),
        connection_timeout=5,
        max_transaction_retry_time=10,
    )


def run(query: str, **params: Any) -> list[dict[str, Any]]:
    """Tek bir Cypher sorgusu çalıştırır ve kayıtları sözlük listesi olarak döner."""
    records, _, _ = get_driver().execute_query(Query(query), params, database_="neo4j")
    return [r.data() for r in records]


def close_driver() -> None:
    if get_driver.cache_info().currsize:
        get_driver().close()
        get_driver.cache_clear()
