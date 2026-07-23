"""Use case ``ReconcileJobs`` — сверка зависших заданий (§10).

Плечо «команда → событие» — at-least-once, но не at-most-once: команда
может потеряться в брокере, а embedding-service — умереть, не ответив. Без
сверки такое задание висит вечно, и товар навсегда остаётся без векторов.

Здесь мы находим команды, на которые дольше таймаута нет ответа, и
переспрашиваем: новая команда с ``attempt+1`` и экспоненциальным backoff.
Исходная команда остаётся в своём статусе — если ответ на неё всё-таки
придёт, ``ApplyEmbeddingResult`` применит его идемпотентно.
"""

from datetime import timedelta
from uuid import uuid5

from indexing_service.application.dto.reports import JobsReport
from indexing_service.application.embedding_command import (
    build_command_message,
)
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.unit_of_work import UnitOfWork
from indexing_service.application.request_id import deterministic_request_id
from indexing_service.domain.entities.embedding_request import EmbeddingRequest
from indexing_service.domain.value_objects.job_status import RequestStatus


class ReconcileJobs:
    """Переспрашивает эмбеддинги по зависшим командам."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        *,
        job_timeout_s: float,
        max_request_attempts: int,
        retry_backoff_s: float,
        retry_backoff_cap_s: float,
        batch: int = 100,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._job_timeout_s = job_timeout_s
        self._max_request_attempts = max_request_attempts
        self._retry_backoff_s = retry_backoff_s
        self._retry_backoff_cap_s = retry_backoff_cap_s
        self._batch = batch

    async def execute(self) -> JobsReport:
        """Находит зависшие команды и ставит повторные."""
        async with self._uow as uow:
            now = self._clock.now()
            cutoff = now - timedelta(seconds=self._job_timeout_s)
            stale = await uow.requests.find_stale(cutoff, limit=self._batch)
            requeued = exhausted = 0
            for request in stale:
                job = await uow.jobs.get(request.job_id)
                if job is None or job.is_terminal:
                    continue  # задание уже закрыто — переспрашивать нечего
                if request.attempt + 1 >= self._max_request_attempts:
                    exhausted += 1
                    continue
                if await self._requeue(uow, request, job, now):
                    requeued += 1
            await uow.commit()
        return JobsReport(
            stale=len(stale), requeued=requeued, exhausted=exhausted
        )

    async def _requeue(self, uow, request, job, now) -> bool:
        attempt = request.attempt + 1
        new_id = deterministic_request_id(job.job_id, attempt, request.items)
        if await uow.requests.get(new_id) is not None:
            return False  # такую попытку уже ставили — не плодим дубликат
        delay = min(
            self._retry_backoff_s * 2 ** (attempt - 1),
            self._retry_backoff_cap_s,
        )
        retry = EmbeddingRequest(
            request_id=new_id,
            job_id=job.job_id,
            attempt=attempt,
            items=request.items,
            status=RequestStatus.PENDING,
            next_attempt_at=now + timedelta(seconds=delay),
            created_at=now,
            requested_at=None,
            received_at=None,
        )
        await uow.requests.add(retry)
        await uow.outbox.add_many(
            [
                build_command_message(
                    retry,
                    model=job.expected_model,
                    message_id=uuid5(new_id.value, "outbox"),
                    occurred_at=now,
                    next_attempt_at=retry.next_attempt_at,
                )
            ]
        )
        return True
