"""Настройки сервиса (pydantic-settings).

Переменные окружения читаются с префиксом ``INDEXING_`` (напр.
``INDEXING_QDRANT_URL``). Значения по умолчанию рассчитаны на локальный
docker-compose стек.
"""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingMode(StrEnum):
    """Режим эмбеддера: in-process, внешний сервис или фейк для тестов."""

    LOCAL = "local"
    REMOTE = "remote"
    FAKE = "fake"


class SourceMode(StrEnum):
    """Источник данных на горячем пути (§13, тема 1)."""

    EVENT = "event"
    HYBRID = "hybrid"
    FETCH = "fetch"


class Settings(BaseSettings):
    """Конфигурация indexing-service."""

    model_config = SettingsConfigDict(
        env_prefix="INDEXING_",
        env_file=".env",
        extra="ignore",
    )

    # Брокер (источник событий каталога).
    rabbitmq_dsn: str = "amqp://guest:guest@localhost:5672/"
    # Qdrant (поисковая read-model).
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_alias: str = "products"
    # catalog-service (repair / reindex / reconcile).
    catalog_base_url: str = "http://localhost:8000"
    # Домен.
    default_currency: str = "RUB"
    # Эмбеддер (BGE-M3).
    embedding_mode: EmbeddingMode = EmbeddingMode.LOCAL
    embedding_model: str = "BAAI/bge-m3"
    embedding_revision: str = ""
    embedding_device: str = "cpu"
    embedding_dim: int = 1024
    # Источник данных на горячем пути.
    source_mode: SourceMode = SourceMode.HYBRID
    # Консюмер: QoS и retry/DLQ.
    prefetch_count: int = 32
    max_attempts: int = 5
    retry_ttl_ms: int = 30000
    log_level: str = "INFO"
    # Наблюдаемость: OTLP-endpoint трейсинга (пусто = трейсинг выключен).
    otlp_endpoint: str | None = None
    service_name: str = "indexing-service"


def get_settings() -> Settings:
    """Возвращает настройки, прочитанные из окружения/`.env`."""
    return Settings()
