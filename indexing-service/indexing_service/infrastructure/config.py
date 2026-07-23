"""Настройки сервиса (pydantic-settings).

Переменные окружения читаются с префиксом ``INDEXING_`` (напр.
``INDEXING_QDRANT_URL``). Значения по умолчанию рассчитаны на локальный
docker-compose стек.
"""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # PostgreSQL (indexing jobs + transactional outbox).
    database_url: str = (
        "postgresql+asyncpg://indexing:indexing@localhost:5432/indexing"
    )
    sql_echo: bool = False
    # Qdrant (поисковая read-model).
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_alias: str = "products"
    # catalog-service (repair / reindex / reconcile).
    catalog_base_url: str = "http://localhost:8000"
    # Домен.
    default_currency: str = "RUB"
    # Размерность векторов embedding-service (провижининг + валидация).
    embedding_dim: int = 1024
    # Источник данных на горячем пути.
    source_mode: SourceMode = SourceMode.HYBRID
    # Консюмер: QoS и retry/DLQ.
    prefetch_count: int = 32
    max_attempts: int = 5
    retry_ttl_ms: int = 30000
    # Outbox relay (публикация команд на эмбеддинг в embedding.jobs).
    outbox_poll_interval_s: float = 1.0
    outbox_max_attempts: int = 10
    outbox_batch_size: int = 100
    # Ожидаемая модель эмбеддингов: пусто = доверяем текущей модели
    # embedding-service, дрейф ловит reconcile (Q3).
    expected_model: str | None = None
    # Операционный лимит батча embedding-service: длиннее команду не шлём.
    max_texts: int = 32
    # Максимум попыток эмбеддинга одного чанка (INFERENCE_FAILED) до DLQ.
    max_item_attempts: int = 5
    # Экспоненциальный backoff ретраев чанка: база и потолок задержки.
    item_retry_backoff_s: float = 5.0
    item_retry_backoff_cap_s: float = 300.0
    log_level: str = "INFO"
    # Наблюдаемость: OTLP-endpoint трейсинга (пусто = трейсинг выключен).
    otlp_endpoint: str | None = None
    service_name: str = "indexing-service"


def get_settings() -> Settings:
    """Возвращает настройки, прочитанные из окружения/`.env`."""
    return Settings()
