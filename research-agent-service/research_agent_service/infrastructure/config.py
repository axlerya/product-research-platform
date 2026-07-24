"""Настройки сервиса (pydantic-settings, префикс RESEARCH_AGENT_)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация из окружения (RESEARCH_AGENT_*) и .env."""

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_AGENT_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "research-agent-service"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://research_agent:research_agent"
        "@localhost:5432/research_agent"
    )
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_dsn: str = "amqp://guest:guest@localhost:5672/"

    # Пусто = distributed tracing выключен.
    otlp_endpoint: str = ""


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек (для composition root)."""
    return Settings()
