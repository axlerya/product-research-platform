"""Настройки сервиса (pydantic-settings).

Переменные окружения читаются с префиксом ``CATALOG_`` (напр.
``CATALOG_DATABASE_URL``). Значения по умолчанию рассчитаны на локальный
docker-compose стек.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация сервиса каталога."""

    model_config = SettingsConfigDict(
        env_prefix="CATALOG_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://catalog:catalog@localhost:5432/catalog"
    )
    rabbitmq_dsn: str = "amqp://guest:guest@localhost:5672/"
    default_currency: str = "RUB"
    sql_echo: bool = False
    outbox_poll_interval_s: float = 1.0
    outbox_batch_size: int = 100
    outbox_max_attempts: int = 10
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Возвращает настройки, прочитанные из окружения/`.env`."""
    return Settings()
