"""Round-trip тесты Data Mapper без БД (ORM <-> домен)."""

from datetime import UTC, datetime
from uuid import UUID

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
from indexing_service.infrastructure.db.mappers import (
    EmbeddingRequestMapper,
    IndexingJobMapper,
)

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _job() -> IndexingJob:
    return IndexingJob(
        job_id=JobId(UUID(int=1)),
        product_id=ProductId(UUID(int=2)),
        sku=Sku("PROD-123"),
        aggregate_version=3,
        content_version=2,
        content_hash=ContentHash.of("текст документа"),
        action=IndexAction.FULL_INDEX,
        target_collection="products_v2",
        expected_model="bge-m3",
        status=JobStatus.AWAITING,
        chunks=(
            Chunk(
                chunk_ix=0,
                text_id="p2::0",
                point_id="p2-0",
                status=ChunkStatus.PENDING,
                attempts=1,
            ),
            Chunk(
                chunk_ix=1,
                text_id="p2::1",
                point_id="p2-1",
                status=ChunkStatus.OK,
                attempts=0,
            ),
        ),
        created_at=_NOW,
        updated_at=_NOW,
        applied_at=None,
    )


def _request() -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id=RequestId(UUID(int=10)),
        job_id=JobId(UUID(int=1)),
        attempt=0,
        items=(
            RequestItem(text_id="p2::0", text="первый чанк"),
            RequestItem(text_id="p2::1", text="второй чанк"),
        ),
        status=RequestStatus.PENDING,
        next_attempt_at=None,
        created_at=_NOW,
        requested_at=None,
        received_at=None,
    )


def test_job_round_trips_through_orm():
    job = _job()
    restored = IndexingJobMapper.to_domain(IndexingJobMapper.to_orm(job))
    assert restored == job


def test_job_chunks_serialize_as_ordered_dicts():
    orm = IndexingJobMapper.to_orm(_job())
    assert orm.chunks == [
        {
            "chunk_ix": 0,
            "text_id": "p2::0",
            "point_id": "p2-0",
            "status": "pending",
            "attempts": 1,
        },
        {
            "chunk_ix": 1,
            "text_id": "p2::1",
            "point_id": "p2-1",
            "status": "ok",
            "attempts": 0,
        },
    ]


def test_request_round_trips_through_orm():
    request = _request()
    restored = EmbeddingRequestMapper.to_domain(
        EmbeddingRequestMapper.to_orm(request)
    )
    assert restored == request


def test_request_items_serialize_as_ordered_dicts():
    orm = EmbeddingRequestMapper.to_orm(_request())
    assert orm.items == [
        {"text_id": "p2::0", "text": "первый чанк"},
        {"text_id": "p2::1", "text": "второй чанк"},
    ]
