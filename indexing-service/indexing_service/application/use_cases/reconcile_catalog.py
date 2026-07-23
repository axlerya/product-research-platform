"""Use case ``ReconcileCatalog`` — сверка каталога и Qdrant (§9).

Лечит дрейф от потерянных событий, DLQ и — главное — устаревание метрик
(``update_metrics`` в catalog не эмитит событие, но бампает версию, §9.1).
Дрейф без смены текста/модели чинится ``set_payload`` без ре-эмбеддинга.

Векторы reconcile не считает: где нужен пересчёт, он заводит задание через
``RequestEmbedding``, как и горячий путь. Осиротевшие точки по-прежнему
закрывает tombstone напрямую — там embedding-service не нужен.
"""

from indexing_service.application.document_builder import to_product_document
from indexing_service.application.dto.embedding_job import EmbeddingJobRequest
from indexing_service.application.dto.reports import ReconcileReport
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.exceptions import IndexingError
from indexing_service.application.indexer import tombstone
from indexing_service.application.payload import pending_payload
from indexing_service.application.ports.catalog_gateway import CatalogGateway
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.entities.product_document import ProductDocument
from indexing_service.domain.exceptions import DomainError
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import IndexAction


class ReconcileCatalog:
    """Сверяет каталог с Qdrant и чинит расхождения идемпотентно (§6)."""

    def __init__(
        self,
        *,
        index: VectorIndex,
        request_embedding: RequestEmbedding,
        catalog: CatalogGateway,
        clock: Clock,
        expected_model: str | None = None,
        batch: int = 100,
    ) -> None:
        self._index = index
        self._request_embedding = request_embedding
        self._catalog = catalog
        self._clock = clock
        self._expected_model = expected_model
        self._batch = batch

    async def execute(self) -> ReconcileReport:
        """Прогоняет обе стороны сверки и возвращает отчёт."""
        matched = indexed = repaired = tombstoned = errors = 0
        catalog_ids: set[ProductId] = set()

        async for snapshot in self._catalog.iter_products(batch=self._batch):
            product_id = ProductId(snapshot.product_id)
            catalog_ids.add(product_id)
            try:
                outcome = await self._reconcile_one(snapshot, product_id)
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
        self, snapshot: ProductSnapshot, product_id: ProductId
    ) -> str:
        watermark = await self._index.get_watermark(product_id)
        document = to_product_document(snapshot)
        if watermark is None:
            await self._index.upsert_payload(
                product_id,
                pending_payload(document, indexed_at=self._clock.now()),
            )
            await self._request_job(document)
            return "indexed"

        model_ok = (
            self._expected_model is None
            or watermark.model_version == self._expected_model
        )
        if (
            watermark.aggregate_version >= snapshot.aggregate_version
            and model_ok
        ):
            return "matched"

        text_same = (
            watermark.content_hash is not None
            and watermark.content_hash.value == document.content_hash().value
        )
        # Дрейф метрик/цены без смены текста и модели → payload без задания.
        # pending_payload не несёт водяных знаков, поэтому уже посчитанные
        # векторы не объявляются устаревшими.
        await self._index.set_payload(
            product_id,
            pending_payload(document, indexed_at=self._clock.now()),
        )
        if not (text_same and model_ok):
            await self._request_job(document)
        return "repaired"

    async def _request_job(self, document: ProductDocument) -> None:
        """Ставит задание на пересчёт векторов товара."""
        await self._request_embedding.handle(
            EmbeddingJobRequest(
                product_id=document.product_id,
                sku=document.sku,
                aggregate_version=document.aggregate_version,
                content_version=document.aggregate_version,
                content_hash=document.content_hash(),
                text=document.search_text(),
                action=IndexAction.REEMBED,
            )
        )
