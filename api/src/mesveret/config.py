from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"

    database_url: str = "postgresql+psycopg://mesveret:mesveret@localhost:5433/mesveret"

    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "mesveret-neo4j"

    ledger_leader_url: str = "http://localhost:8101"
    ledger_node_urls: str = "http://localhost:8101,http://localhost:8102,http://localhost:8103"
    ledger_token: str = "dev-ledger-token"

    jwt_secret: str = "dev-jwt-secret-change-me-before-production-0001"
    jwt_ttl_hours: int = 12
    shade_key: str = "dev-shade-key-change-me"

    graph_backend: str = "neo4j"  # neo4j | memory
    ledger_backend: str = "http"  # http | fake

    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 5.0

    cors_origins: str = "*"
    # Demo modunun terminale bastığı bağlantılar için istemcinin adresi.
    client_url: str = "http://localhost:8081"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def ledger_nodes(self) -> list[str]:
        return [u.strip() for u in self.ledger_node_urls.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
