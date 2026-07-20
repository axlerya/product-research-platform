"""Composition root консюмера: сборка зависимостей из настроек.

Единственное место, знающее все слои. Не покрывается unit-тестами
(проводка проверяется e2e/через docker-compose).
"""

from dataclasses import dataclass

import httpx
from faststream.rabbit import RabbitBroker
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine

from indexing_service.application.use_cases.process_catalog_event import (
    ProcessCatalogEvent,
)
from indexing_service.application.use_cases.reconcile_catalog import (
    ReconcileCatalog,
)
from indexing_service.application.use_cases.reindex_catalog import (
    ReindexCatalog,
)
from indexing_service.infrastructure.catalog.http_client import (
    HttpCatalogClient,
)
from indexing_service.infrastructure.config import EmbeddingMode, Settings
from indexing_service.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)
from indexing_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingModel,
)
from indexing_service.infrastructure.messaging.broker import (
    RabbitEmbeddingPublisher,
    build_broker,
)
from indexing_service.infrastructure.outbox.relay import OutboxPublisher
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
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

    async def aclose(self) -> None:
        await self.qdrant.close()
        await self.http.aclose()


def _build_embedder(settings: Settings):
    if settings.embedding_mode is EmbeddingMode.LOCAL:
        from indexing_service.infrastructure.embedding.bge_m3 import (
            load_bge_m3,
        )

        return load_bge_m3(
            model=settings.embedding_model,
            revision=settings.embedding_revision,
            device=settings.embedding_device,
            dim=settings.embedding_dim,
        )
    return DeterministicEmbeddingModel(dim=settings.embedding_dim)


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
    use_case = ProcessCatalogEvent(
        index=QdrantVectorIndex(
            qdrant, collection=settings.collection_alias
        ),
        embedder=_build_embedder(settings),
        catalog=HttpCatalogClient(http, base_url=settings.catalog_base_url),
        clock=SystemClock(),
    )
    return ConsumerDeps(use_case=use_case, qdrant=qdrant, http=http)


@dataclass
class BatchDeps:
    """Зависимости batch-операций (reindex/reconcile/provision)."""

    reindex: ReindexCatalog
    reconcile: ReconcileCatalog
    provisioner: CollectionProvisioner
    alias: str
    qdrant: AsyncQdrantClient
    http: httpx.AsyncClient

    async def aclose(self) -> None:
        await self.qdrant.close()
        await self.http.aclose()


@dataclass
class RelayDeps:
    """Зависимости outbox-relay + закрытие ресурсов."""

    broker: RabbitBroker
    publisher: OutboxPublisher
    interval: float
    engine: AsyncEngine

    async def aclose(self) -> None:
        await self.engine.dispose()


def build_relay(settings: Settings) -> RelayDeps:
    """Собирает outbox-relay (движок БД + брокер + publisher)."""
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
    )


async def build_batch(settings: Settings) -> BatchDeps:
    """Собирает use cases reindex/reconcile и провижинер коллекции."""
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key or None
    )
    http = httpx.AsyncClient(timeout=30.0)
    embedder = _build_embedder(settings)
    catalog = HttpCatalogClient(http, base_url=settings.catalog_base_url)
    clock = SystemClock()
    physical = f"{settings.collection_alias}_v1"
    return BatchDeps(
        reindex=ReindexCatalog(
            admin=QdrantIndexAdmin(qdrant, dim=settings.embedding_dim),
            embedder=embedder,
            catalog=catalog,
            clock=clock,
        ),
        reconcile=ReconcileCatalog(
            index=QdrantVectorIndex(
                qdrant, collection=settings.collection_alias
            ),
            embedder=embedder,
            catalog=catalog,
            clock=clock,
        ),
        provisioner=CollectionProvisioner(
            qdrant, collection=physical, dim=settings.embedding_dim
        ),
        alias=settings.collection_alias,
        qdrant=qdrant,
        http=http,
    )
