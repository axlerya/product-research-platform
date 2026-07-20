"""Use case ``ApplyEmbeddingResult`` — приём события ``generated.v1`` (§6).

Консюмер результата: находит команду/job по ``request_id``, валидирует,
пишет успешные чанки в Qdrant (guard по ``content_version``), классифицирует
item-ошибки (Q2) и — в одной транзакции — обновляет статусы job/request и
кладёт ретрай-команды в outbox. Идемпотентен к повторной доставке
(``request.status == done`` / job терминальна → no-op).

Rechunk для ``TOKENS_EXCEEDED``/``TEXT_TOO_LONG`` — отдельный следующий шаг;
сейчас такие item помечаются перманентно упавшими.
"""

from dataclasses import replace
from uuid import uuid5

from indexing_service.application.dto.chunk_write import ChunkWrite
from indexing_service.application.dto.embedding_result import (
    EmbeddingResult,
    EmbeddingResultItem,
)
from indexing_service.application.embedding_command import build_command_message
from indexing_service.application.exceptions import EventValidationError
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.embedding_sink import (
    EmbeddingResultSink,
)
from indexing_service.application.ports.unit_of_work import UnitOfWork
from indexing_service.application.request_id import deterministic_request_id
from indexing_service.domain.entities.embedding_request import (
    EmbeddingRequest,
    RequestItem,
)
from indexing_service.domain.entities.indexing_job import Chunk, IndexingJob
from indexing_service.domain.value_objects.identifiers import RequestId
from indexing_service.domain.value_objects.job_status import (
    EmbeddingErrorCode,
    JobStatus,
    RequestStatus,
)


class ApplyEmbeddingResult:
    """Применяет результат эмбеддинга к Qdrant и состоянию jobs."""

    def __init__(
        self,
        uow: UnitOfWork,
        sink: EmbeddingResultSink,
        clock: Clock,
        *,
        expected_dim: int,
        max_item_attempts: int,
    ) -> None:
        self._uow = uow
        self._sink = sink
        self._clock = clock
        self._expected_dim = expected_dim
        self._max_item_attempts = max_item_attempts

    async def handle(self, result: EmbeddingResult) -> None:
        """Обрабатывает событие-результат (идемпотентно)."""
        async with self._uow as uow:
            request = await uow.requests.get(RequestId(result.request_id))
            if request is None or request.status is RequestStatus.DONE:
                return  # сирота или дубликат → no-op
            job = await uow.jobs.get(request.job_id)
            if job is None or job.is_terminal:
                return
            self._validate(result, job)

            now = self._clock.now()
            retry_items: list[RequestItem] = []
            for item in result.items:
                chunk = job.chunk_by_text_id(item.text_id)
                if item.is_ok:
                    await self._sink.apply_chunk(
                        self._to_write(job, chunk, result.model_version, item)
                    )
                    job = job.mark_chunk_ok(item.text_id)
                else:
                    job, retry = self._on_error(job, chunk, item, request)
                    if retry is not None:
                        retry_items.append(retry)

            request = replace(
                request, status=RequestStatus.DONE, received_at=now
            )
            await uow.requests.update(request)
            if retry_items:
                await self._enqueue_retry(uow, job, request, retry_items, now)

            job = job.recompute_status()
            applied_at = now if job.status is JobStatus.DONE else job.applied_at
            job = replace(job, updated_at=now, applied_at=applied_at)
            await uow.jobs.upsert(job)
            await uow.commit()

    def _validate(self, result: EmbeddingResult, job: IndexingJob) -> None:
        if result.dim != self._expected_dim:
            raise EventValidationError(
                f"dim={result.dim}, ожидался {self._expected_dim}"
            )
        known = {chunk.text_id for chunk in job.chunks}
        for item in result.items:
            if item.text_id not in known:
                raise EventValidationError(
                    f"text_id вне job: {item.text_id!r}"
                )

    def _on_error(
        self,
        job: IndexingJob,
        chunk: Chunk,
        item: EmbeddingResultItem,
        request: EmbeddingRequest,
    ) -> tuple[IndexingJob, RequestItem | None]:
        code = item.error.code
        if code is EmbeddingErrorCode.INFERENCE_FAILED:
            if chunk.attempts + 1 < self._max_item_attempts:
                job = job.mark_chunk_retrying(item.text_id)
                text = self._text_of(request, item.text_id)
                return job, RequestItem(text_id=item.text_id, text=text)
            return job.mark_chunk_failed(item.text_id), None
        # EMPTY_TEXT — перманентно; TOKENS_EXCEEDED/TEXT_TOO_LONG — до rechunk.
        return job.mark_chunk_failed(item.text_id), None

    async def _enqueue_retry(
        self,
        uow: UnitOfWork,
        job: IndexingJob,
        request: EmbeddingRequest,
        retry_items: list[RequestItem],
        now,
    ) -> None:
        attempt = request.attempt + 1
        items = tuple(retry_items)
        new_id = deterministic_request_id(job.job_id, attempt, items)
        retry = EmbeddingRequest(
            request_id=new_id,
            job_id=job.job_id,
            attempt=attempt,
            items=items,
            status=RequestStatus.PENDING,
            next_attempt_at=None,
            created_at=now,
            requested_at=None,
            received_at=None,
        )
        await uow.requests.add(retry)
        message = build_command_message(
            retry,
            model=job.expected_model,
            message_id=uuid5(new_id.value, "outbox"),
            occurred_at=now,
        )
        await uow.outbox.add_many([message])

    @staticmethod
    def _text_of(request: EmbeddingRequest, text_id: str) -> str:
        for item in request.items:
            if item.text_id == text_id:
                return item.text
        raise EventValidationError(f"нет текста для ретрая: {text_id!r}")

    @staticmethod
    def _to_write(
        job: IndexingJob,
        chunk: Chunk,
        model_version: str,
        item: EmbeddingResultItem,
    ) -> ChunkWrite:
        return ChunkWrite(
            point_id=chunk.point_id,
            product_id=job.product_id.value,
            sku=job.sku.value,
            chunk_ix=chunk.chunk_ix,
            content_version=job.content_version,
            aggregate_version=job.aggregate_version,
            model_version=model_version,
            dense=item.dense,
            sparse=item.sparse,
            token_count=item.token_count,
        )
