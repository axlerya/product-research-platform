"""Composition root: сборка зависимостей из настроек.

Единственное место, знающее все слои. Проводка проверяется integration/e2e,
а не unit-тестами (вне coverage).
"""

import logging
from dataclasses import dataclass

from prometheus_client import CollectorRegistry

from embedding_service.application.use_cases.describe_model import DescribeModel
from embedding_service.application.use_cases.embed_documents import (
    EmbedDocuments,
)
from embedding_service.application.use_cases.embed_queries import EmbedQueries
from embedding_service.application.use_cases.embed_query import EmbedQuery
from embedding_service.application.use_cases.rerank_documents import (
    RerankDocuments,
)
from embedding_service.application.use_cases.warmup_model import WarmupModel
from embedding_service.infrastructure.config import Settings
from embedding_service.infrastructure.embedding.batching_provider import (
    BatchingEmbeddingProvider,
)
from embedding_service.infrastructure.embedding.factory import build_provider
from embedding_service.infrastructure.observability.metrics import (
    Metrics,
    build_metrics,
)
from embedding_service.infrastructure.observability.reranker_metrics import (
    RerankerMetrics,
    build_reranker_metrics,
)
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.infrastructure.reranking.concurrency import (
    ConcurrencyGuardedRerankerProvider,
)
from embedding_service.infrastructure.reranking.factory import (
    build_reranker_provider,
)
from embedding_service.infrastructure.services.clock import SystemClock
from embedding_service.infrastructure.services.id_generator import (
    UuidGenerator,
)

_logger = logging.getLogger(__name__)


@dataclass
class Deps:
    """Собранные зависимости сервиса (одна модель на обе плоскости).

    Reranker-часть опциональна и заполняется только при ``RERANKER_ENABLED``;
    её жизненный цикл изолирован от BGE-M3.
    """

    settings: Settings
    provider: BatchingEmbeddingProvider
    embed_documents: EmbedDocuments
    embed_query: EmbedQuery
    embed_queries: EmbedQueries
    warmup: WarmupModel
    describe: DescribeModel
    registry: CollectorRegistry
    metrics: Metrics
    clock: SystemClock
    id_generator: UuidGenerator
    reranker_settings: RerankerSettings | None = None
    reranker_provider: ConcurrencyGuardedRerankerProvider | None = None
    rerank_documents: RerankDocuments | None = None
    reranker_metrics: RerankerMetrics | None = None

    @property
    def reranker_enabled(self) -> bool:
        """Собран ли reranker (включён и провайдер построен)."""
        return self.rerank_documents is not None

    @property
    def reranker_configured(self) -> bool:
        """Просил ли оператор reranker (``RERANKER_ENABLED``).

        Отличает «выключен» (RerankerService не регистрируется → Rerank
        отвечает UNIMPLEMENTED) от «включён, но провайдер не создался»
        (регистрируется в состоянии NOT_SERVING → Rerank UNAVAILABLE).
        """
        settings = self.reranker_settings
        return settings is not None and settings.enabled

    async def aclose(self) -> None:
        await self.provider.aclose()
        if self.reranker_provider is not None:
            await self.reranker_provider.aclose()


def build_deps(
    settings: Settings, reranker_settings: RerankerSettings | None = None
) -> Deps:
    """Строит провайдер ОДИН РАЗ и все use cases поверх него.

    При ``reranker_settings.enabled`` дополнительно строит reranker-провайдер
    (отдельная модель) и его use case; иначе reranker-поля остаются ``None`` и
    сервис работает в прежнем режиме.
    """
    provider = build_provider(settings)
    doc_limits = settings.document_limits()
    query_limits = settings.query_limits()
    registry = CollectorRegistry()

    reranker_provider = None
    rerank_documents = None
    reranker_metrics = None
    if reranker_settings is not None and reranker_settings.enabled:
        # Безопасная граница: сбой создания reranker (веса, CUDA, отсутствующий
        # extra) НЕ должен ронять embedding-сервис — деградируем до «выключен».
        try:
            reranker_provider = build_reranker_provider(reranker_settings)
            rerank_documents = RerankDocuments(
                reranker_provider, reranker_settings.limits()
            )
            reranker_metrics = build_reranker_metrics(registry)
        except Exception as exc:
            # Без секретов: тип и текст ошибки, но не настройки/окружение.
            _logger.warning(
                "не удалось создать reranker-провайдер (%s: %s); "
                "сервис продолжает работу без reranker",
                type(exc).__name__,
                exc,
            )
            reranker_provider = None
            rerank_documents = None
            reranker_metrics = None

    return Deps(
        settings=settings,
        provider=provider,
        embed_documents=EmbedDocuments(provider, doc_limits),
        embed_query=EmbedQuery(provider, query_limits),
        embed_queries=EmbedQueries(provider, query_limits),
        warmup=WarmupModel(provider),
        describe=DescribeModel(provider),
        registry=registry,
        metrics=build_metrics(registry),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
        reranker_settings=reranker_settings,
        reranker_provider=reranker_provider,
        rerank_documents=rerank_documents,
        reranker_metrics=reranker_metrics,
    )
