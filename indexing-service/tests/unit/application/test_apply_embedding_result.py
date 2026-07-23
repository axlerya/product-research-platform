"""Тесты use case ``ApplyEmbeddingResult`` на фейках (§6, §9)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from indexing_service.application.dto.embedding_result import (
    EmbeddingResult,
    EmbeddingResultItem,
    ItemError,
)
from indexing_service.application.exceptions import EventValidationError
from indexing_service.application.use_cases.apply_embedding_result import (
    ApplyEmbeddingResult,
)
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
    EmbeddingErrorCode,
    IndexAction,
    JobStatus,
    RequestStatus,
)
from indexing_service.domain.value_objects.sku import Sku

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_APPLIED = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
_JOB_ID = JobId(UUID(int=1))
_REQ_ID = RequestId(UUID(int=10))
_PRODUCT = ProductId(UUID(int=2))


class _FakeJobs:
    def __init__(self, jobs):
        self.store = {job.job_id: job for job in jobs}

    async def upsert(self, job):
        self.store[job.job_id] = job

    async def get(self, job_id):
        return self.store.get(job_id)

    async def get_by_product(self, product_id, content_version):
        return None


class _FakeRequests:
    def __init__(self, requests):
        self.store = {req.request_id: req for req in requests}

    async def add(self, request):
        self.store[request.request_id] = request

    async def get(self, request_id):
        return self.store.get(request_id)

    async def update(self, request):
        self.store[request.request_id] = request


class _FakeOutbox:
    def __init__(self):
        self.messages = []

    async def add_many(self, messages):
        self.messages.extend(messages)


class _FakeUoW:
    def __init__(self, jobs, requests):
        self.jobs = _FakeJobs(jobs)
        self.requests = _FakeRequests(requests)
        self.outbox = _FakeOutbox()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


class _FakeSink:
    def __init__(self):
        self.writes = []

    async def apply_chunk(self, write):
        self.writes.append(write)
        return True


class _Clock:
    def now(self):
        return _APPLIED


def _chunk(ix, *, status=ChunkStatus.PENDING, attempts=0):
    return Chunk(
        chunk_ix=ix,
        text_id=f"c{ix}",
        point_id=f"p{ix}",
        status=status,
        attempts=attempts,
    )


def _job(chunks, *, status=JobStatus.AWAITING):
    return IndexingJob(
        job_id=_JOB_ID,
        product_id=_PRODUCT,
        sku=Sku("PROD-1"),
        aggregate_version=2,
        content_version=3,
        content_hash=ContentHash.of("t"),
        action=IndexAction.FULL_INDEX,
        target_collection=None,
        expected_model="bge-m3",
        status=status,
        chunks=tuple(chunks),
        created_at=_NOW,
        updated_at=_NOW,
        applied_at=None,
    )


def _request(items, *, attempt=0, status=RequestStatus.AWAITING):
    return EmbeddingRequest(
        request_id=_REQ_ID,
        job_id=_JOB_ID,
        attempt=attempt,
        items=tuple(items),
        status=status,
        next_attempt_at=None,
        created_at=_NOW,
        requested_at=_NOW,
        received_at=None,
    )


def _ok(text_id, dense=(0.1, 0.2, 0.3)):
    return EmbeddingResultItem(
        text_id=text_id,
        dense=dense,
        sparse=None,
        token_count=7,
        error=None,
    )


def _err(text_id, code):
    return EmbeddingResultItem(
        text_id=text_id,
        dense=None,
        sparse=None,
        token_count=None,
        error=ItemError(code=code, message="oops"),
    )


def _result(items, *, dim=3):
    return EmbeddingResult(
        request_id=_REQ_ID.value,
        model_version="bge-m3",
        dim=dim,
        items=tuple(items),
    )


def _use_case(
    uow,
    sink,
    *,
    max_item_attempts=5,
    retry_backoff_s=5.0,
    retry_backoff_cap_s=300.0,
):
    return ApplyEmbeddingResult(
        uow,
        sink,
        _Clock(),
        expected_dim=3,
        max_item_attempts=max_item_attempts,
        retry_backoff_s=retry_backoff_s,
        retry_backoff_cap_s=retry_backoff_cap_s,
    )


async def test_all_ok_writes_and_marks_done():
    uow = _FakeUoW(
        [_job([_chunk(0), _chunk(1)])],
        [_request([RequestItem("c0", "a"), RequestItem("c1", "b")])],
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(_result([_ok("c0"), _ok("c1")]))

    assert uow.committed
    assert {w.point_id for w in sink.writes} == {"p0", "p1"}
    assert sink.writes[0].content_version == 3
    assert sink.writes[0].aggregate_version == 2
    job = uow.jobs.store[_JOB_ID]
    assert job.status is JobStatus.DONE
    assert job.applied_at == _APPLIED
    assert uow.requests.store[_REQ_ID].status is RequestStatus.DONE


async def test_partial_result_leaves_job_awaiting():
    uow = _FakeUoW(
        [_job([_chunk(0), _chunk(1)])],
        [_request([RequestItem("c0", "a")])],
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(_result([_ok("c0")]))

    assert len(sink.writes) == 1
    assert uow.jobs.store[_JOB_ID].status is JobStatus.AWAITING


async def test_duplicate_delivery_is_noop():
    uow = _FakeUoW(
        [_job([_chunk(0)])],
        [_request([RequestItem("c0", "a")], status=RequestStatus.DONE)],
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(_result([_ok("c0")]))

    assert sink.writes == []
    assert not uow.committed


async def test_orphan_request_is_noop():
    uow = _FakeUoW([_job([_chunk(0)])], [])
    sink = _FakeSink()
    await _use_case(uow, sink).handle(_result([_ok("c0")]))
    assert sink.writes == []
    assert not uow.committed


async def test_terminal_job_is_noop():
    uow = _FakeUoW(
        [_job([_chunk(0, status=ChunkStatus.OK)], status=JobStatus.DONE)],
        [_request([RequestItem("c0", "a")])],
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(_result([_ok("c0")]))
    assert sink.writes == []
    assert not uow.committed


async def test_inference_failed_enqueues_retry():
    uow = _FakeUoW(
        [_job([_chunk(0)])],
        [_request([RequestItem("c0", "текст-c0")])],
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(
        _result([_err("c0", EmbeddingErrorCode.INFERENCE_FAILED)])
    )

    job = uow.jobs.store[_JOB_ID]
    assert job.status is JobStatus.PARTIALLY_FAILED
    assert job.chunk_by_text_id("c0").status is ChunkStatus.RETRYING
    # добавлена ретрай-команда (attempt=1) + строка outbox
    assert len(uow.requests.store) == 2
    assert len(uow.outbox.messages) == 1
    retry = next(r for r in uow.requests.store.values() if r.attempt == 1)
    assert retry.items[0].text == "текст-c0"
    assert uow.outbox.messages[0].event_type == (
        "embedding.documents.requested.v1"
    )


class _SpyMetrics:
    def __init__(self) -> None:
        self.applied: list[bool] = []
        self.finished: list[tuple[float, bool]] = []

    def chunk_applied(self, *, applied: bool) -> None:
        self.applied.append(applied)

    def job_finished(self, *, latency_s: float, failed: bool) -> None:
        self.finished.append((latency_s, failed))


async def test_metrics_record_applied_chunks_and_job_latency():
    uow = _FakeUoW(
        [_job([_chunk(0)])], [_request([RequestItem("c0", "a")])]
    )
    metrics = _SpyMetrics()
    use_case = ApplyEmbeddingResult(
        uow,
        _FakeSink(),
        _Clock(),
        expected_dim=3,
        max_item_attempts=5,
        retry_backoff_s=5.0,
        retry_backoff_cap_s=300.0,
        metrics=metrics,
    )

    await use_case.handle(_result([_ok("c0")]))

    assert metrics.applied == [True]
    # job создана в _NOW, применена в _APPLIED — ровно час
    assert metrics.finished == [(3600.0, False)]


async def test_metrics_not_reported_while_job_in_flight():
    uow = _FakeUoW(
        [_job([_chunk(0), _chunk(1)])],
        [_request([RequestItem("c0", "a")])],
    )
    metrics = _SpyMetrics()
    use_case = ApplyEmbeddingResult(
        uow,
        _FakeSink(),
        _Clock(),
        expected_dim=3,
        max_item_attempts=5,
        retry_backoff_s=5.0,
        retry_backoff_cap_s=300.0,
        metrics=metrics,
    )

    await use_case.handle(_result([_ok("c0")]))

    assert metrics.applied == [True]
    assert metrics.finished == []  # второй чанк ещё в работе


async def test_retry_is_delayed_by_backoff():
    """Первый ретрай откладывается на базовую задержку (§8, §10)."""
    uow = _FakeUoW(
        [_job([_chunk(0)])], [_request([RequestItem("c0", "текст")])]
    )
    await _use_case(uow, _FakeSink()).handle(
        _result([_err("c0", EmbeddingErrorCode.INFERENCE_FAILED)])
    )

    retry = next(r for r in uow.requests.store.values() if r.attempt == 1)
    assert retry.next_attempt_at == _APPLIED + timedelta(seconds=5)
    # relay не опубликует команду раньше срока
    assert uow.outbox.messages[0].next_attempt_at == retry.next_attempt_at


async def test_backoff_grows_exponentially():
    """Каждая следующая попытка ждёт вдвое дольше."""
    uow = _FakeUoW(
        [_job([_chunk(0, status=ChunkStatus.RETRYING, attempts=2)])],
        [_request([RequestItem("c0", "текст")], attempt=2)],
    )
    await _use_case(uow, _FakeSink()).handle(
        _result([_err("c0", EmbeddingErrorCode.INFERENCE_FAILED)])
    )

    retry = next(r for r in uow.requests.store.values() if r.attempt == 3)
    # attempt=3 → 5 * 2**2 = 20 c
    assert retry.next_attempt_at == _APPLIED + timedelta(seconds=20)


async def test_backoff_is_capped():
    """Задержка не растёт выше потолка."""
    uow = _FakeUoW(
        [_job([_chunk(0, status=ChunkStatus.RETRYING, attempts=3)])],
        [_request([RequestItem("c0", "текст")], attempt=3)],
    )
    await _use_case(uow, _FakeSink(), retry_backoff_cap_s=12.0).handle(
        _result([_err("c0", EmbeddingErrorCode.INFERENCE_FAILED)])
    )

    retry = next(r for r in uow.requests.store.values() if r.attempt == 4)
    assert retry.next_attempt_at == _APPLIED + timedelta(seconds=12)


async def test_inference_failed_exhausted_marks_failed():
    uow = _FakeUoW(
        [_job([_chunk(0, status=ChunkStatus.RETRYING, attempts=4)])],
        [_request([RequestItem("c0", "a")], attempt=4)],
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(
        _result([_err("c0", EmbeddingErrorCode.INFERENCE_FAILED)])
    )

    job = uow.jobs.store[_JOB_ID]
    assert job.status is JobStatus.FAILED
    assert job.chunk_by_text_id("c0").status is ChunkStatus.FAILED
    assert uow.outbox.messages == []


async def test_empty_text_is_permanent():
    uow = _FakeUoW(
        [_job([_chunk(0)])], [_request([RequestItem("c0", "")])]
    )
    sink = _FakeSink()
    await _use_case(uow, sink).handle(
        _result([_err("c0", EmbeddingErrorCode.EMPTY_TEXT)])
    )
    job = uow.jobs.store[_JOB_ID]
    assert job.status is JobStatus.FAILED
    assert uow.outbox.messages == []


async def test_tokens_exceeded_splits_chunk_and_requeues():
    """Слишком длинный текст дробится, чанк заменяется под-чанками (Q2)."""
    long_text = "раз два три четыре пять шесть семь восемь девять"
    uow = _FakeUoW(
        [_job([_chunk(0)])], [_request([RequestItem("c0", long_text)])]
    )
    await _use_case(uow, _FakeSink()).handle(
        _result([_err("c0", EmbeddingErrorCode.TOKENS_EXCEEDED)])
    )

    job = uow.jobs.store[_JOB_ID]
    assert len(job.chunks) > 1
    assert job.status is JobStatus.PARTIALLY_FAILED
    # нулевой под-чанк переиспользует точку родителя — она не осиротеет
    assert job.chunks[0].point_id == "p0"
    assert {c.point_id for c in job.chunks} == {c.text_id for c in job.chunks}
    # новая команда несёт ровно под-чанки, и вместе они дают исходный текст
    retry = next(r for r in uow.requests.store.values() if r.attempt == 1)
    assert [i.text_id for i in retry.items] == [c.text_id for c in job.chunks]
    assert " ".join(i.text for i in retry.items) == long_text
    assert len(uow.outbox.messages) == 1


async def test_text_too_long_also_rechunks():
    uow = _FakeUoW(
        [_job([_chunk(0)])],
        [_request([RequestItem("c0", "первый кусок второй кусок")])],
    )
    await _use_case(uow, _FakeSink()).handle(
        _result([_err("c0", EmbeddingErrorCode.TEXT_TOO_LONG)])
    )
    assert len(uow.jobs.store[_JOB_ID].chunks) > 1


async def test_rechunk_counts_towards_item_attempts():
    """Под-чанки наследуют счётчик попыток — дробление не бесконечно."""
    uow = _FakeUoW(
        [_job([_chunk(0, attempts=1)])],
        [_request([RequestItem("c0", "раз два три четыре")])],
    )
    await _use_case(uow, _FakeSink()).handle(
        _result([_err("c0", EmbeddingErrorCode.TOKENS_EXCEEDED)])
    )
    assert all(c.attempts == 2 for c in uow.jobs.store[_JOB_ID].chunks)


async def test_rechunk_exhausted_attempts_marks_failed():
    uow = _FakeUoW(
        [_job([_chunk(0, attempts=4)])],
        [_request([RequestItem("c0", "раз два три четыре")])],
    )
    await _use_case(uow, _FakeSink(), max_item_attempts=5).handle(
        _result([_err("c0", EmbeddingErrorCode.TOKENS_EXCEEDED)])
    )
    job = uow.jobs.store[_JOB_ID]
    assert job.status is JobStatus.FAILED
    assert len(job.chunks) == 1
    assert uow.outbox.messages == []


async def test_unsplittable_text_is_permanent():
    """Дробить нечего — перманентный отказ, а не бесконечный rechunk."""
    uow = _FakeUoW([_job([_chunk(0)])], [_request([RequestItem("c0", "я")])])
    await _use_case(uow, _FakeSink()).handle(
        _result([_err("c0", EmbeddingErrorCode.TOKENS_EXCEEDED)])
    )
    job = uow.jobs.store[_JOB_ID]
    assert job.status is JobStatus.FAILED
    assert len(job.chunks) == 1
    assert uow.outbox.messages == []


async def test_dim_mismatch_rejected():
    uow = _FakeUoW([_job([_chunk(0)])], [_request([RequestItem("c0", "a")])])
    with pytest.raises(EventValidationError):
        await _use_case(uow, _FakeSink()).handle(
            _result([_ok("c0", dense=(0.1, 0.2))], dim=2)
        )


async def test_unknown_text_id_rejected():
    uow = _FakeUoW([_job([_chunk(0)])], [_request([RequestItem("c0", "a")])])
    with pytest.raises(EventValidationError):
        await _use_case(uow, _FakeSink()).handle(_result([_ok("c9")]))
