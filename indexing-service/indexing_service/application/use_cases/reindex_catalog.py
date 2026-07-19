"""Use case ``ReindexCatalog`` — полная переиндексация blue-green (§8).

Провижинит новую коллекцию, заливает весь каталог из REST (source of
truth) новой моделью, затем атомарно переключает alias. Идемпотентно.
"""

from indexing_service.application.dto.reports import ReindexReport
from indexing_service.application.exceptions import IndexingError
from indexing_service.application.indexer import index_snapshot
from indexing_service.application.ports.catalog_gateway import CatalogGateway
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.embedding_model import EmbeddingModel
from indexing_service.application.ports.vector_index_admin import (
    VectorIndexAdmin,
)
from indexing_service.domain.exceptions import DomainError


class ReindexCatalog:
    """Backfill каталога в новую коллекцию + атомарный свап алиаса."""

    def __init__(
        self,
        *,
        admin: VectorIndexAdmin,
        embedder: EmbeddingModel,
        catalog: CatalogGateway,
        clock: Clock,
        batch: int = 128,
    ) -> None:
        self._admin = admin
        self._embedder = embedder
        self._catalog = catalog
        self._clock = clock
        self._batch = batch

    async def execute(
        self, *, target_collection: str, alias: str
    ) -> ReindexReport:
        """Провижинит, заливает каталог и свапает alias на новую коллекцию."""
        await self._admin.provision(target_collection)
        writer = self._admin.writer(target_collection)
        indexed = errors = 0
        async for snapshot in self._catalog.iter_products(batch=self._batch):
            try:
                await index_snapshot(
                    snapshot,
                    index=writer,
                    embedder=self._embedder,
                    clock=self._clock,
                )
                indexed += 1
            except (IndexingError, DomainError):
                errors += 1
        await self._admin.swap_alias(alias, target_collection)
        return ReindexReport(indexed=indexed, errors=errors)
