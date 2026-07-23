"""Use case ``ReindexCatalog`` — полная переиндексация blue-green (§8).

Провижинит новую коллекцию, заливает в неё карточки товаров из REST (source
of truth) и заводит на каждый товар задание на эмбеддинг с
``target_collection`` — эпохой переиндексации. Векторы считает
embedding-service, результаты ``ApplyEmbeddingResult`` пишет сразу в новую
коллекцию, не трогая живой alias.

Свап alias — отдельная операция (``swap``): переключаться можно только когда
эпоха готова (Q6), а это происходит сильно позже постановки заданий.
"""

from indexing_service.application.document_builder import to_product_document
from indexing_service.application.dto.embedding_job import EmbeddingJobRequest
from indexing_service.application.dto.reports import ReindexReport, SwapReport
from indexing_service.application.exceptions import IndexingError
from indexing_service.application.payload import pending_payload
from indexing_service.application.ports.catalog_gateway import CatalogGateway
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.unit_of_work import UnitOfWork
from indexing_service.application.ports.vector_index_admin import (
    VectorIndexAdmin,
)
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.exceptions import DomainError
from indexing_service.domain.value_objects.job_status import (
    IndexAction,
    JobStatus,
)


class ReindexCatalog:
    """Заводит эпоху переиндексации и переключает alias по готовности."""

    def __init__(
        self,
        *,
        admin: VectorIndexAdmin,
        request_embedding: RequestEmbedding,
        uow: UnitOfWork,
        catalog: CatalogGateway,
        clock: Clock,
        batch: int = 128,
    ) -> None:
        self._admin = admin
        self._request_embedding = request_embedding
        self._uow = uow
        self._catalog = catalog
        self._clock = clock
        self._batch = batch

    async def execute(self, *, target_collection: str) -> ReindexReport:
        """Провижинит коллекцию и ставит задания на весь каталог."""
        await self._admin.provision(target_collection)
        writer = self._admin.writer(target_collection)
        queued = skipped = errors = 0
        async for snapshot in self._catalog.iter_products(batch=self._batch):
            try:
                created = await self._queue_one(
                    snapshot, writer, target_collection
                )
            except (IndexingError, DomainError):
                errors += 1
                continue
            if created:
                queued += 1
            else:
                skipped += 1
        return ReindexReport(queued=queued, skipped=skipped, errors=errors)

    async def swap(
        self,
        *,
        target_collection: str,
        alias: str,
        min_ready: float = 1.0,
    ) -> SwapReport:
        """Переключает alias, если эпоха готова (Q6).

        Args:
            target_collection: Коллекция эпохи.
            alias: Публичный alias поиска.
            min_ready: Требуемая доля завершённых заданий (1.0 — все).

        Returns:
            Отчёт с прогрессом эпохи и признаком, переключён ли alias.
        """
        async with self._uow as uow:
            counts = await uow.jobs.epoch_counts(target_collection)
        total = sum(counts.values())
        done = counts.get(JobStatus.DONE, 0)
        failed = counts.get(JobStatus.FAILED, 0)
        report = SwapReport(
            swapped=False,
            total=total,
            done=done,
            failed=failed,
            pending=total - done - failed,
        )
        if total == 0:
            return report  # эпохи нет — переключать не на что
        if done / total < min_ready:
            return report
        await self._admin.swap_alias(alias, target_collection)
        return SwapReport(
            swapped=True,
            total=report.total,
            done=report.done,
            failed=report.failed,
            pending=report.pending,
        )

    async def _queue_one(
        self, snapshot, writer, target_collection: str
    ) -> bool:
        """Пишет карточку в новую коллекцию и ставит задание."""
        document = to_product_document(snapshot)
        await writer.upsert_payload(
            document.product_id,
            pending_payload(document, indexed_at=self._clock.now()),
        )
        return await self._request_embedding.handle(
            EmbeddingJobRequest(
                product_id=document.product_id,
                sku=document.sku,
                aggregate_version=document.aggregate_version,
                content_version=document.aggregate_version,
                content_hash=document.content_hash(),
                text=document.search_text(),
                action=IndexAction.FULL_INDEX,
                target_collection=target_collection,
            )
        )
