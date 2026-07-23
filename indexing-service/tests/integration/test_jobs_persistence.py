"""Integration: хранилище jobs/requests/outbox против реального Postgres.

Схема накатывается настоящими миграциями Alembic (см. conftest). Проверяем
round-trip репозиториев, идемпотентность upsert, атомарность UoW и FK/uq.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from indexing_service.application.outbox_message import OutboxMessage
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
from indexing_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _job(
    *,
    job_id: JobId | None = None,
    product_id: ProductId | None = None,
    content_version: int = 2,
    status: JobStatus = JobStatus.AWAITING,
    applied_at: datetime | None = None,
) -> IndexingJob:
    return IndexingJob(
        job_id=job_id or JobId(uuid4()),
        product_id=product_id or ProductId(uuid4()),
        sku=Sku("PROD-42"),
        aggregate_version=3,
        content_version=content_version,
        content_hash=ContentHash.of("текст"),
        action=IndexAction.FULL_INDEX,
        target_collection="products_v2",
        expected_model="bge-m3",
        status=status,
        chunks=(
            Chunk(
                chunk_ix=0,
                text_id="c0",
                point_id="p0",
                status=ChunkStatus.PENDING,
                attempts=0,
            ),
        ),
        created_at=_NOW,
        updated_at=_NOW,
        applied_at=applied_at,
    )


def _request(
    job_id: JobId, *, request_id: RequestId | None = None
) -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id=request_id or RequestId(uuid4()),
        job_id=job_id,
        attempt=0,
        items=(RequestItem(text_id="c0", text="первый чанк"),),
        status=RequestStatus.PENDING,
        next_attempt_at=None,
        created_at=_NOW,
        requested_at=None,
        received_at=None,
    )


def _outbox_for(request: EmbeddingRequest) -> OutboxMessage:
    return OutboxMessage(
        id=uuid4(),
        aggregate_type="embedding_request",
        aggregate_id=request.request_id.value,
        event_type="embedding.documents.requested.v1",
        payload={"data": {"request_id": str(request.request_id.value)}},
        occurred_at=_NOW,
    )


async def test_job_round_trips_through_repository(sessionmaker_):
    job = _job()
    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.jobs.upsert(job)
        await uow.commit()

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        by_id = await uow.jobs.get(job.job_id)
        by_product = await uow.jobs.get_by_product(
            job.product_id, job.content_version, job.target_collection
        )

    assert by_id == job
    assert by_product == job


async def test_job_upsert_is_idempotent(sessionmaker_):
    job = _job()
    updated = _job(
        job_id=job.job_id,
        product_id=job.product_id,
        status=JobStatus.DONE,
        applied_at=_NOW,
    )

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.jobs.upsert(job)
        await uow.commit()
    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.jobs.upsert(updated)
        await uow.commit()

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        stored = await uow.jobs.get(job.job_id)
    assert stored is not None
    assert stored.status is JobStatus.DONE
    assert stored.applied_at == _NOW


async def test_unit_of_work_persists_job_request_outbox_atomically(
    sessionmaker_,
):
    job = _job()
    request = _request(job.job_id)
    message = _outbox_for(request)

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.jobs.upsert(job)
        await uow.requests.add(request)
        await uow.outbox.add_many([message])
        await uow.commit()

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        assert await uow.jobs.get(job.job_id) == job
        assert await uow.requests.get(request.request_id) == request

    async with sessionmaker_() as session:
        outbox_count = await session.scalar(
            text("SELECT count(*) FROM outbox")
        )
    assert outbox_count == 1


async def test_unit_of_work_rolls_back_on_error(sessionmaker_):
    job = _job()
    with pytest.raises(RuntimeError):
        async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
            await uow.jobs.upsert(job)
            raise RuntimeError("boom")

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        assert await uow.jobs.get(job.job_id) is None


async def test_request_requires_existing_job(sessionmaker_):
    orphan = _request(JobId(uuid4()))
    with pytest.raises(IntegrityError):
        async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
            await uow.requests.add(orphan)


async def test_same_product_content_version_is_unique(sessionmaker_):
    product_id = ProductId(uuid4())
    first = _job(product_id=product_id, content_version=2)
    clash = _job(product_id=product_id, content_version=2)

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.jobs.upsert(first)
        await uow.commit()

    with pytest.raises(IntegrityError):
        async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
            await uow.jobs.upsert(clash)
            await uow.commit()
