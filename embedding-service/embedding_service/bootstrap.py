"""Composition root: сборка зависимостей из настроек.

Единственное место, знающее все слои. Проводка проверяется integration/e2e,
а не unit-тестами (вне coverage).
"""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry

from embedding_service.application.use_cases.describe_model import DescribeModel
from embedding_service.application.use_cases.embed_documents import (
    EmbedDocuments,
)
from embedding_service.application.use_cases.embed_queries import EmbedQueries
from embedding_service.application.use_cases.embed_query import EmbedQuery
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
from embedding_service.infrastructure.services.clock import SystemClock
from embedding_service.infrastructure.services.id_generator import (
    UuidGenerator,
)


@dataclass
class Deps:
    """Собранные зависимости сервиса (одна модель на обе плоскости)."""

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

    async def aclose(self) -> None:
        await self.provider.aclose()


def build_deps(settings: Settings) -> Deps:
    """Строит провайдер ОДИН РАЗ и все use cases поверх него."""
    provider = build_provider(settings)
    doc_limits = settings.document_limits()
    query_limits = settings.query_limits()
    registry = CollectorRegistry()
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
    )
