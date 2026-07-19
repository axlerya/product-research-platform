"""Use case ``ReconcileCatalog`` — сверка каталога и Qdrant (§9).

Лечит дрейф от потерянных событий, DLQ и — главное — устаревание метрик
(``update_metrics`` в catalog не эмитит событие, но бампает версию, §9.1).
Дрейф без смены текста/модели чинится ``set_payload`` без ре-эмбеддинга.
"""

from indexing_service.application.document_builder import to_product_document
from indexing_service.application.dto.reports import ReconcileReport
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.exceptions import IndexingError
from indexing_service.application.indexer import index_snapshot, tombstone
from indexing_service.application.payload import full_payload
from indexing_service.application.ports.catalog_gateway import CatalogGateway
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.embedding_model import EmbeddingModel
from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.domain.exceptions import DomainError
from indexing_service.domain.value_objects.identifiers import ProductId


class ReconcileCatalog:
    """Сверяет каталог с Qdrant и чинит расхождения идемпотентно (§6)."""

    def __init__(
        self,
        *,
        index: VectorIndex,
        embedder: EmbeddingModel,
        catalog: CatalogGateway,
        clock: Clock,
        batch: int = 100,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._catalog = catalog
        self._clock = clock
        self._batch = batch

    async def execute(self) -> ReconcileReport:
        """Прогоняет обе стороны сверки и возвращает отчёт."""
        matched = indexed = repaired = tombstoned = errors = 0
        model_key = self._embedder.model_id.key
        catalog_ids: set[ProductId] = set()

        async for snapshot in self._catalog.iter_products(batch=self._batch):
            product_id = ProductId(snapshot.product_id)
            catalog_ids.add(product_id)
            try:
                outcome = await self._reconcile_one(
                    snapshot, product_id, model_key
                )
            except (IndexingError, DomainError):
                errors += 1
                continue
            if outcome == "matched":
                matched += 1
            elif outcome == "indexed":
                indexed += 1
            else:
                repaired += 1

        async for entry in self._index.scroll_watermarks():
            if entry.product_id in catalog_ids or entry.is_deleted:
                continue
            try:
                await tombstone(
                    entry.product_id,
                    index=self._index,
                    clock=self._clock,
                    version=entry.watermark.aggregate_version,
                )
                tombstoned += 1
            except IndexingError:
                errors += 1

        return ReconcileReport(
            matched=matched,
            indexed=indexed,
            repaired=repaired,
            tombstoned=tombstoned,
            errors=errors,
        )

    async def _reconcile_one(
        self, snapshot: ProductSnapshot, product_id: ProductId, model_key: str
    ) -> str:
        watermark = await self._index.get_watermark(product_id)
        if watermark is None:
            await index_snapshot(
                snapshot,
                index=self._index,
                embedder=self._embedder,
                clock=self._clock,
            )
            return "indexed"
        if (
            watermark.aggregate_version >= snapshot.aggregate_version
            and watermark.model_version == model_key
        ):
            return "matched"

        document = to_product_document(snapshot)
        text_same = (
            watermark.content_hash is not None
            and watermark.content_hash.value == document.content_hash().value
        )
        if text_same and watermark.model_version == model_key:
            # Дрейф метрик/цены без смены текста → payload без ре-эмбеддинга.
            await self._index.set_payload(
                product_id,
                full_payload(
                    document,
                    model_version=model_key,
                    indexed_at=self._clock.now(),
                ),
            )
        else:
            await index_snapshot(
                snapshot,
                index=self._index,
                embedder=self._embedder,
                clock=self._clock,
            )
        return "repaired"
