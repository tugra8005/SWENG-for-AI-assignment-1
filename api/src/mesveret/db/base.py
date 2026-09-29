from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mesveret.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI bağımlılığı: istek başına bir oturum."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def create_schema() -> None:
    from mesveret.db import models  # noqa: F401  (tabloları kaydeder)

    engine = get_engine()
    Base.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(engine: Engine) -> list[str]:
    """Alembic yok: şema ``create_all`` ile kurulur, o da var olan tabloya sütun eklemez. Eski bir
    yığında yeni sütunlar boş (NULL) olarak eklenir; ``seed --reset`` şemayı zaten baştan kurar,
    bu yalnızca o komuta ulaşılabilsin diye vardır."""
    added = []
    existing = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not existing.has_table(table.name):
                continue
            have = {c["name"] for c in existing.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    kind = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {kind}'))
                    added.append(f"{table.name}.{col.name}")
    return added


def drop_schema() -> None:
    from mesveret.db import models  # noqa: F401

    Base.metadata.drop_all(get_engine())
