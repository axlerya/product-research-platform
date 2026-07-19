"""Composition root консюмера: сборка зависимостей из настроек.

Единственное место, знающее все слои. Не покрывается unit-тестами
(проводка проверяется e2e/через docker-compose).
"""

from dataclasses import dataclass

import httpx
from qdrant_client import AsyncQdrantClient

from indexing_service.application.use_cases.process_catalog_event import (
    ProcessCatalogEvent,
)
from indexing_service.infrastructure.catalog.http_client import (
    HttpCatalogClient,
)
from indexing_service.infrastructure.config import EmbeddingMode, Settings
from indexing_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingModel,
)
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
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
