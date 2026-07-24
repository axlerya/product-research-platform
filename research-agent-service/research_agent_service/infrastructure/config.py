"""Настройки сервиса (pydantic-settings, префикс RESEARCH_AGENT_)."""

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmSettings(BaseModel):
    """LLM через OpenAI-совместимый эндпоинт с кастомным base_url.

    Переменные окружения — с префиксом RESEARCH_AGENT_LLM__ (например
    RESEARCH_AGENT_LLM__BASE_URL, RESEARCH_AGENT_LLM__MODEL).
    """

    model: str = "qwen3"
    base_url: str = "http://localhost:8001/v1"
    api_key: str = "sk-local"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: float = 60.0
    max_retries: int = 3
    service_tier: str = "auto"
    enable_thinking: bool = False


class Settings(BaseSettings):
    """Конфигурация из окружения (RESEARCH_AGENT_*) и .env."""

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_AGENT_",
        env_file=".env",
        env_nested_delimiter="__",
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

    embedding_grpc_target: str = "localhost:50051"
    reranker_grpc_target: str = "localhost:50051"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "products"
    catalog_base_url: str = "http://localhost:8080"

    # Провайдер web-поиска: "tavily" | "serper".
    web_search_provider: str = "tavily"
    web_search_api_key: str = ""

    # Relay outbox: период дренажа и размер партии.
    relay_interval_s: float = 1.0
    relay_batch_size: int = 100

    llm: LlmSettings = LlmSettings()

    # Пусто = distributed tracing выключен.
    otlp_endpoint: str = ""


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек (для composition root)."""
    return Settings()
