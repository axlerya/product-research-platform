"""Настройки reranker (pydantic-settings, префикс ``RERANKER_``).

Отдельный класс и отдельный файл — конфигурация reranker полностью изолирована
от ``EMBEDDING_``-настроек (``infrastructure/config.py`` не тронут). По
умолчанию ``enabled=False`` — сервис стартует в прежнем режиме без reranker.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from embedding_service.domain.value_objects.reranking.limits import (
    RerankLimits,
)
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)


class RerankerSettings(BaseSettings):
    """Конфигурация reranker из окружения (``RERANKER_*``) и ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="RERANKER_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
    )

    # --- Переключатель ---
    enabled: bool = False

    # --- Провайдер ---
    provider_mode: Literal["bge_reranker", "deterministic"] = "bge_reranker"
    model: str = "BAAI/bge-reranker-v2-m3"
    revision: str = ""
    normalized: bool = True

    # --- Устройство и точность ---
    device: Literal["auto", "cpu", "cuda"] = "auto"
    precision: Literal["fp32", "fp16", "bf16"] = "fp16"
    cpu_fallback: bool = False

    # --- Батчинг и конкурентность ---
    max_batch_size: int = 32
    inference_timeout_s: float = 10.0
    max_concurrent_inferences: int = 1

    # --- Лимиты запроса ---
    max_documents: int = 256
    max_query_chars: int = 8_000
    max_document_chars: int = 32_000
    max_total_bytes: int = 4_194_304

    def build_model_id(self) -> RerankerModelId:
        """Собирает идентификатор reranker-модели (== ``model_version``)."""
        return RerankerModelId(
            name=self.model,
            revision=self.revision or "unknown",
            normalized=self.normalized,
        )

    def limits(self) -> RerankLimits:
        """Лимиты rerank-запроса."""
        return RerankLimits(
            max_documents=self.max_documents,
            max_query_chars=self.max_query_chars,
            max_document_chars=self.max_document_chars,
            max_total_bytes=self.max_total_bytes,
        )


@lru_cache
def get_reranker_settings() -> RerankerSettings:
    """Кэшированный синглтон настроек reranker (для composition root)."""
    return RerankerSettings()
