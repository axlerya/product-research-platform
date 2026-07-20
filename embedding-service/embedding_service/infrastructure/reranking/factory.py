"""Фабрика reranker-провайдера из настроек (composition-помощник).

Возвращает ``ConcurrencyGuardedRerankerProvider`` поверх реальной
bge-reranker-v2-m3 или детерминированного FAKE (по ``provider_mode``).
"""

from embedding_service.application.ports.reranker_provider import (
    RerankerProvider,
)
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.infrastructure.reranking.concurrency import (
    ConcurrencyGuardedRerankerProvider,
)
from embedding_service.infrastructure.reranking.deterministic import (
    DeterministicRerankerProvider,
)


def build_reranker_provider(
    settings: RerankerSettings,
) -> ConcurrencyGuardedRerankerProvider:
    """Собирает guard поверх подлежащего провайдера по настройкам."""
    return ConcurrencyGuardedRerankerProvider(
        _build_inner(settings),
        max_concurrent=settings.max_concurrent_inferences,
        batch_size=settings.max_batch_size,
        timeout_s=settings.inference_timeout_s,
    )


def _build_inner(settings: RerankerSettings) -> RerankerProvider:
    if settings.provider_mode == "deterministic":
        return DeterministicRerankerProvider(model_id=settings.build_model_id())
    return _load_bge(settings)


def _load_bge(  # pragma: no cover - тяжёлая проводка (torch/FlagEmbedding)
    settings: RerankerSettings,
) -> RerankerProvider:
    from embedding_service.infrastructure.reranking.bge_reranker import (
        load_bge_reranker_provider,
    )

    return load_bge_reranker_provider(
        model=settings.model,
        revision=settings.revision,
        device=settings.device,
        precision=settings.precision,
        normalized=settings.normalized,
    )
