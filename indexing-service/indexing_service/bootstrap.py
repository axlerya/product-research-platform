"""Composition root консюмера: сборка зависимостей из настроек.

Единственное место, знающее все слои. Не покрывается unit-тестами
(проводка проверяется e2e/через docker-compose).
"""

from dataclasses import dataclass

import httpx
from faststream.rabbit import RabbitBroker
from prometheus_client import CollectorRegistry
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine

from indexing_service.application.use_cases.apply_embedding_result import (
    ApplyEmbeddingResult,
)
from indexing_service.application.use_cases.process_catalog_event import (
    ProcessCatalogEvent,
)
from indexing_service.application.use_cases.reconcile_catalog import (
    ReconcileCatalog,
)
from indexing_service.application.use_cases.reconcile_jobs import (
    ReconcileJobs,
)
from indexing_service.application.use_cases.reindex_catalog import (
    ReindexCatalog,
)
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.infrastructure.catalog.http_client import (
    HttpCatalogClient,
)
from indexing_service.infrastructure.config import Settings
from indexing_service.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)
from indexing_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from indexing_service.infrastructure.messaging.broker import (
    RabbitEmbeddingPublisher,
    build_broker,
)
from indexing_service.infrastructure.observability.metrics import (
    BacklogGauges,
    build_metrics,
)
from indexing_service.infrastructure.outbox.relay import OutboxPublisher
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.embedding_sink import (
    QdrantEmbeddingSink,
)
from indexing_service.infrastructure.qdrant.index_admin import QdrantIndexAdmin
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)
from indexing_service.infrastructure.services.clock import SystemClock


@dataclass
class ConsumerDeps:
    """Зависимости консюмера + закрытие ресурсов."""

    use_case: ProcessCatalogEvent
    qdrant: AsyncQdrantClient
    http: httpx.AsyncClient
    engine: AsyncEngine

    async def aclose(self) -> None:
        await self.qdrant.close()
        await self.http.aclose()
        await self.engine.dispose()


async def build_consumer(settings: Settings) -> ConsumerDeps:
    """Собирает ``ProcessCatalogEvent`` со всеми адаптерами."""
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key or None
    )
    physical = f"{settings.collection_alias}_v1"
    provisioner = CollectionProvisioner(
        qdrant, collection=physical, dim=settings.embedding_dim
    )
    await provisioner.ensure()
    await provisioner.point_alias(settings.collection_alias)

    http = httpx.AsyncClient(timeout=10.0)
    engine = build_engine(settings)
    clock = SystemClock()
    use_case = ProcessCatalogEvent(
        index=QdrantVectorIndex(
            qdrant, collection=settings.collection_alias
        ),
        request_embedding=RequestEmbedding(
            SqlAlchemyUnitOfWork(build_sessionmaker(engine)),
            clock,
            chunker=SingleDocument(),
            expected_model=settings.expected_model,
            max_texts=settings.max_texts,
        ),
        catalog=HttpCatalogClient(http, base_url=settings.catalog_base_url),
        clock=clock,
        expected_model=settings.expected_model,
    )
    return ConsumerDeps(
        use_case=use_case, qdrant=qdrant, http=http, engine=engine
    )


@dataclass
class BatchDeps:
    """Зависимости batch-операций (reindex/reconcile/provision)."""

    reindex: ReindexCatalog
    reconcile: ReconcileCatalog
    reconcile_jobs: ReconcileJobs
    provisioner: CollectionProvisioner
    alias: str
    qdrant: AsyncQdrantClient
    http: httpx.AsyncClient
    engine: AsyncEngine

    async def aclose(self) -> None:
        await self.qdrant.close()
        await self.http.aclose()
        await self.engine.dispose()


@dataclass
class RelayDeps:
    """Зависимости outbox-relay + закрытие ресурсов."""

    broker: RabbitBroker
    publisher: OutboxPublisher
    interval: float
    engine: AsyncEngine
    gauges: BacklogGauges | None = None

    async def aclose(self) -> None:
        await self.engine.dispose()


def build_relay(
    settings: Settings, *, registry: CollectorRegistry | None = None
) -> RelayDeps:
    """Собирает outbox-relay (движок БД + брокер + publisher + метрики)."""
    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    broker = build_broker(settings)
    publisher = OutboxPublisher(
        sessionmaker,
        RabbitEmbeddingPublisher(broker),
        max_attempts=settings.outbox_max_attempts,
        batch_size=settings.outbox_batch_size,
    )
    return RelayDeps(
        broker=broker,
        publisher=publisher,
        interval=settings.outbox_poll_interval_s,
        engine=engine,
        gauges=(
            BacklogGauges(sessionmaker, registry)
            if registry is not None
            else None
        ),
    )


@dataclass
class ResultConsumerDeps:
    """Зависимости консюмера результатов эмбеддинга + закрытие ресурсов."""

    use_case: ApplyEmbeddingResult
    engine: AsyncEngine
    qdrant: AsyncQdrantClient

    async def aclose(self) -> None:
        await self.qdrant.close()
        await self.engine.dispose()


def build_result_consumer(
    settings: Settings, *, registry: CollectorRegistry | None = None
) -> ResultConsumerDeps:
    """Собирает ``ApplyEmbeddingResult`` (UoW + Qdrant-sink + метрики)."""
    engine = build_engine(settings)
    uow = SqlAlchemyUnitOfWork(build_sessionmaker(engine))
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key or None
    )
    use_case = ApplyEmbeddingResult(
        uow,
        QdrantEmbeddingSink(qdrant, collection=settings.collection_alias),
        SystemClock(),
        expected_dim=settings.embedding_dim,
        max_item_attempts=settings.max_item_attempts,
        retry_backoff_s=settings.item_retry_backoff_s,
        retry_backoff_cap_s=settings.item_retry_backoff_cap_s,
        metrics=build_metrics(registry) if registry is not None else None,
    )
    return ResultConsumerDeps(use_case=use_case, engine=engine, qdrant=qdrant)


async def build_batch(settings: Settings) -> BatchDeps:
    """Собирает use cases reindex/reconcile и провижинер коллекции."""
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key or None
    )
    http = httpx.AsyncClient(timeout=30.0)
    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    catalog = HttpCatalogClient(http, base_url=settings.catalog_base_url)
    clock = SystemClock()
    physical = f"{settings.collection_alias}_v1"

    def request_embedding() -> RequestEmbedding:
        # Своя UoW на use case: у каждого своя транзакционная граница.
        return RequestEmbedding(
            SqlAlchemyUnitOfWork(sessionmaker),
            clock,
            chunker=SingleDocument(),
            expected_model=settings.expected_model,
            max_texts=settings.max_texts,
        )

    return BatchDeps(
        reindex=ReindexCatalog(
            admin=QdrantIndexAdmin(qdrant, dim=settings.embedding_dim),
            request_embedding=request_embedding(),
            uow=SqlAlchemyUnitOfWork(sessionmaker),
            catalog=catalog,
            clock=clock,
        ),
        reconcile=ReconcileCatalog(
            index=QdrantVectorIndex(
                qdrant, collection=settings.collection_alias
            ),
            request_embedding=request_embedding(),
            catalog=catalog,
            clock=clock,
            expected_model=settings.expected_model,
        ),
        reconcile_jobs=ReconcileJobs(
            SqlAlchemyUnitOfWork(sessionmaker),
            clock,
            job_timeout_s=settings.job_timeout_s,
            max_request_attempts=settings.max_request_attempts,
            retry_backoff_s=settings.item_retry_backoff_s,
            retry_backoff_cap_s=settings.item_retry_backoff_cap_s,
        ),
        provisioner=CollectionProvisioner(
            qdrant, collection=physical, dim=settings.embedding_dim
        ),
        alias=settings.collection_alias,
        qdrant=qdrant,
        http=http,
        engine=engine,
    )
