"""Тесты ``ReconcileJobs`` — сверка зависших команд (§10)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from indexing_service.application.use_cases.reconcile_jobs import ReconcileJobs
from indexing_service.domain.entities.embedding_request import (
    EmbeddingRequest,
    RequestItem,
)
from indexing_service.domain.entities.indexing_job import Chunk, IndexingJob
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import (
    JobId,
    ProductId,
    RequestId,
)
from indexing_service.domain.value_objects.job_status import (
    ChunkStatus,
    IndexAction,
    JobStatus,
    RequestStatus,
)
from indexing_service.domain.value_objects.sku import Sku
from tests.support.fakes import FakeUnitOfWork

_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
_LONG_AGO = _NOW - timedelta(hours=2)
_JOB_ID = JobId(UUID(int=1))


class _Clock:
    def now(self):
        return _NOW


def _job(*, status=JobStatus.AWAITING) -> IndexingJob:
    return IndexingJob(
        job_id=_JOB_ID,
        product_id=ProductId(UUID(int=2)),
        sku=Sku("PROD-1"),
        aggregate_version=1,
        content_version=1,
        content_hash=ContentHash.of("t"),
        action=IndexAction.FULL_INDEX,
        target_collection=None,
        expected_model=None,
        status=status,
        chunks=(
            Chunk(
                chunk_ix=0,
                text_id="p0",
                point_id="p0",
                status=ChunkStatus.PENDING,
                attempts=0,
            ),
        ),
        created_at=_LONG_AGO,
        updated_at=_LONG_AGO,
        applied_at=None,
    )


def _request(*, attempt=0, status=RequestStatus.AWAITING, requested_at=None):
    return EmbeddingRequest(
        request_id=RequestId(UUID(int=10 + attempt)),
        job_id=_JOB_ID,
        attempt=attempt,
        items=(RequestItem(text_id="p0", text="Кружка"),),
        status=status,
        next_attempt_at=None,
        created_at=_LONG_AGO,
        requested_at=requested_at,
        received_at=None,
    )


def _uow_with(*requests) -> FakeUnitOfWork:
    """UoW с уже лежащими в нём командами (они и окажутся зависшими)."""
    uow = FakeUnitOfWork()
    for request in requests:
        uow.requests.store[request.request_id] = request
    return uow


def _use_case(uow, *, max_request_attempts=5, job_timeout_s=900.0):
    return ReconcileJobs(
        uow,
        _Clock(),
        job_timeout_s=job_timeout_s,
        max_request_attempts=max_request_attempts,
        retry_backoff_s=5.0,
        retry_backoff_cap_s=300.0,
    )


async def test_stale_request_is_requeued_with_backoff():
    stale = _request()
    uow = _uow_with(stale)
    await uow.jobs.upsert(_job())

    report = await _use_case(uow).execute()

    assert report.stale == 1
    assert report.requeued == 1
    retry = next(r for r in uow.requests.store.values() if r.attempt == 1)
    assert retry.status is RequestStatus.PENDING
    assert retry.items == stale.items
    assert retry.next_attempt_at == _NOW + timedelta(seconds=5)
    assert len(uow.outbox.messages) == 1
    assert uow.outbox.messages[0].next_attempt_at == retry.next_attempt_at
    assert uow.commits == 1


async def test_terminal_job_is_left_alone():
    uow = _uow_with(_request())
    await uow.jobs.upsert(_job(status=JobStatus.DONE))

    report = await _use_case(uow).execute()

    assert report.requeued == 0
    assert uow.outbox.messages == []


async def test_orphan_request_is_skipped():
    uow = _uow_with(_request())  # job в хранилище нет

    report = await _use_case(uow).execute()

    assert report.requeued == 0
    assert uow.outbox.messages == []


async def test_exhausted_attempts_are_reported_not_requeued():
    uow = _uow_with(_request(attempt=4))
    await uow.jobs.upsert(_job())

    report = await _use_case(uow, max_request_attempts=5).execute()

    assert report.exhausted == 1
    assert report.requeued == 0
    assert uow.outbox.messages == []


async def test_repeated_reconcile_does_not_duplicate_retry():
    """Тот же attempt даёт тот же request_id — дубликата не будет (§9.1)."""
    uow = _uow_with(_request())
    await uow.jobs.upsert(_job())
    use_case = _use_case(uow)

    await use_case.execute()
    second = await use_case.execute()

    assert second.requeued == 0
    assert len(uow.outbox.messages) == 1
