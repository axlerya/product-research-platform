"""Настройки сервиса (pydantic-settings, префикс ``EMBEDDING_``)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits


class Settings(BaseSettings):
    """Конфигурация из окружения (``EMBEDDING_*``) и ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
    )

    # --- Транспорты ---
    rabbitmq_dsn: str = "amqp://guest:guest@localhost:5672/"
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    ops_http_port: int = 8000

    # --- Провайдер эмбеддингов ---
    provider_mode: Literal["bge_m3", "deterministic"] = "bge_m3"
    model: str = "BAAI/bge-m3"
    revision: str = ""
    dim: int = 1024
    pooling: str = "cls"
    normalized: bool = True

    # --- Устройство и точность ---
    device: Literal["auto", "cpu", "cuda"] = "auto"
    precision: Literal["fp32", "fp16", "bf16"] = "fp16"
    cpu_fallback: bool = False

    # --- Батчинг и конкурентность ---
    max_batch_size: int = 16
    batch_wait_ms: int = 50
    query_batch_wait_ms: int = 5
    max_concurrent_inferences: int = 1
    max_queue_size: int = 256
    inference_timeout_s: float = 30.0
    prefetch_count: int = 8

    # --- Лимиты запроса (документы) ---
    doc_max_texts: int = 256
    doc_max_text_chars: int = 32_000
    doc_max_tokens: int = 8192
    doc_max_total_bytes: int = 4_194_304

    # --- Лимиты запроса (запросы) ---
    query_max_texts: int = 32
    query_max_text_chars: int = 8_000
    query_max_tokens: int = 8192
    query_max_total_bytes: int = 262_144

    # --- Консюмер: retry/DLQ ---
    max_attempts: int = 5
    retry_ttl_ms: int = 30_000
    graceful_timeout: int = 30

    # --- Наблюдаемость ---
    otlp_endpoint: str = ""
    service_name: str = "embedding-service"

    def build_model_id(self) -> EmbeddingModelId:
        """Собирает идентификатор модели (== ``model_version`` на проводе)."""
        return EmbeddingModelId(
            name=self.model,
            revision=self.revision or "unknown",
            pooling=self.pooling,
            normalized=self.normalized,
            dim=self.dim,
        )

    def document_limits(self) -> EmbeddingLimits:
        """Лимиты документного батча."""
        return EmbeddingLimits(
            max_texts=self.doc_max_texts,
            max_text_chars=self.doc_max_text_chars,
            max_tokens=self.doc_max_tokens,
            max_total_bytes=self.doc_max_total_bytes,
        )

    def query_limits(self) -> EmbeddingLimits:
        """Лимиты батча запросов."""
        return EmbeddingLimits(
            max_texts=self.query_max_texts,
            max_text_chars=self.query_max_text_chars,
            max_tokens=self.query_max_tokens,
            max_total_bytes=self.query_max_total_bytes,
        )


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек (для composition root)."""
    return Settings()
