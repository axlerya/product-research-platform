"""Фабрика провайдера эмбеддингов из настроек (composition-помощник).

Возвращает ``BatchingEmbeddingProvider`` поверх реального BGE-M3 или
детерминированного FAKE (по ``provider_mode``).
"""

from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from embedding_service.infrastructure.config import Settings
from embedding_service.infrastructure.embedding.batching_provider import (
    BatchingConfig,
    BatchingEmbeddingProvider,
)
from embedding_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingProvider,
)


def build_provider(settings: Settings) -> BatchingEmbeddingProvider:
    """Собирает батчер поверх подлежащего провайдера по настройкам."""
    config = BatchingConfig(
        max_batch_size=settings.max_batch_size,
        batch_wait_ms=settings.batch_wait_ms,
        query_batch_wait_ms=settings.query_batch_wait_ms,
        max_concurrent_inferences=settings.max_concurrent_inferences,
        max_queue_size=settings.max_queue_size,
        inference_timeout_s=settings.inference_timeout_s,
    )
    return BatchingEmbeddingProvider(_build_inner(settings), config)


def _build_inner(settings: Settings) -> EmbeddingProvider:
    if settings.provider_mode == "deterministic":
        return DeterministicEmbeddingProvider(
            model_id=settings.build_model_id()
        )
    return _load_bge(settings)


def _load_bge(  # pragma: no cover - тяжёлая проводка (torch/FlagEmbedding)
    settings: Settings,
) -> EmbeddingProvider:
    from embedding_service.infrastructure.embedding.bge_m3 import (
        load_bge_m3_provider,
    )

    return load_bge_m3_provider(
        model=settings.model,
        revision=settings.revision,
        device=settings.device,
        precision=settings.precision,
        dim=settings.dim,
        pooling=settings.pooling,
        normalized=settings.normalized,
    )
