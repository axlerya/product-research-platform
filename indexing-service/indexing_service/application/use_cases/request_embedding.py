"""Use case ``RequestEmbedding`` — фаза A конвейера (§6, §9).

Не считает векторы сам: строит чанки, заводит ``IndexingJob`` и кладёт
команды ``embedding.documents.requested.v1`` в outbox — всё в ОДНОЙ
транзакции, поэтому «job без команды» и «команда без job» невозможны (§9.2).
Публикацией занимается relay, результат применит ``ApplyEmbeddingResult``.

Идемпотентность — по паре ``(product_id, content_version)``: редоставка
события каталога не плодит задания (§9.1).
"""

from uuid import uuid5

from indexing_service.application.chunk_identity import chunk_point_id
from indexing_service.application.dto.embedding_job import EmbeddingJobRequest
from indexing_service.application.embedding_command import (
    build_command_message,
)
from indexing_service.application.outbox_message import OutboxMessage
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.unit_of_work import UnitOfWork
from indexing_service.application.request_id import deterministic_request_id
from indexing_service.domain.entities.embedding_request import (
    EmbeddingRequest,
    RequestItem,
)
from indexing_service.domain.entities.indexing_job import Chunk, IndexingJob
from indexing_service.domain.services.chunking import ChunkingStrategy
from indexing_service.domain.value_objects.identifiers import JobId
from indexing_service.domain.value_objects.job_status import (
    ChunkStatus,
    JobStatus,
    RequestStatus,
)


class RequestEmbedding:
    """Заводит задание на эмбеддинг и команды к нему (фаза A)."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        *,
        chunker: ChunkingStrategy,
        expected_model: str | None,
        max_texts: int,
    ) -> None:
        if max_texts < 1:
            raise ValueError(f"max_texts < 1: {max_texts}")
        self._uow = uow
        self._clock = clock
        self._chunker = chunker
        self._expected_model = expected_model
        self._max_texts = max_texts

    async def handle(self, request: EmbeddingJobRequest) -> bool:
        """Ставит job и команды на эмбеддинг.

        Args:
            request: Что и на какой версии текста индексировать.

        Returns:
            ``True``, если задание заведено; ``False``, если задание на эту
            версию текста уже есть (редоставка события каталога).
        """
        async with self._uow as uow:
            existing = await uow.jobs.get_by_product(
                request.product_id, request.content_version
            )
            if existing is not None:
                return False
            now = self._clock.now()
            job_id = JobId.new()
            items = self._items(request)
            job = IndexingJob(
                job_id=job_id,
                product_id=request.product_id,
                sku=request.sku,
                aggregate_version=request.aggregate_version,
                content_version=request.content_version,
                content_hash=request.content_hash,
                action=request.action,
                target_collection=request.target_collection,
                expected_model=self._expected_model,
                status=JobStatus.PENDING,
                chunks=self._chunks(items),
                created_at=now,
                updated_at=now,
                applied_at=None,
            )
            await uow.jobs.upsert(job)
            messages: list[OutboxMessage] = []
            for batch in self._batches(items):
                command = EmbeddingRequest(
                    request_id=deterministic_request_id(job_id, 0, batch),
                    job_id=job_id,
                    attempt=0,
                    items=batch,
                    status=RequestStatus.PENDING,
                    next_attempt_at=None,
                    created_at=now,
                    requested_at=None,
                    received_at=None,
                )
                await uow.requests.add(command)
                messages.append(
                    build_command_message(
                        command,
                        model=self._expected_model,
                        message_id=uuid5(command.request_id.value, "outbox"),
                        occurred_at=now,
                    )
                )
            await uow.outbox.add_many(messages)
            await uow.commit()
            return True

    def _items(self, request: EmbeddingJobRequest) -> tuple[RequestItem, ...]:
        """Режет текст на чанки и присваивает им точки Qdrant."""
        pieces = self._chunker.chunk(request.text)
        return tuple(
            RequestItem(
                text_id=chunk_point_id(request.product_id.value, chunk_ix),
                text=piece.value,
            )
            for chunk_ix, piece in enumerate(pieces)
        )

    @staticmethod
    def _chunks(items: tuple[RequestItem, ...]) -> tuple[Chunk, ...]:
        return tuple(
            Chunk(
                chunk_ix=chunk_ix,
                text_id=item.text_id,
                point_id=item.text_id,
                status=ChunkStatus.PENDING,
                attempts=0,
            )
            for chunk_ix, item in enumerate(items)
        )

    def _batches(
        self, items: tuple[RequestItem, ...]
    ) -> list[tuple[RequestItem, ...]]:
        """Бьёт items на команды не длиннее ``max_texts`` (лимит батча)."""
        step = self._max_texts
        return [
            items[start : start + step]
            for start in range(0, len(items), step)
        ]
