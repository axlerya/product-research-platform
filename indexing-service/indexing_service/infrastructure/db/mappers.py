"""Ручной Data Mapper: ORM-модель <-> доменная сущность.

Домену запрещён импорт SQLAlchemy, поэтому маппинг живёт в инфраструктуре.
Чанки job и элементы команды сериализуются в JSONB как список dict'ов с
сохранением порядка.
"""

from typing import Any

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
from indexing_service.infrastructure.db.models import (
    EmbeddingRequestORM,
    IndexingJobORM,
)


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_ix": chunk.chunk_ix,
        "text_id": chunk.text_id,
        "point_id": chunk.point_id,
        "status": chunk.status.value,
        "attempts": chunk.attempts,
    }


def _chunk_from_dict(data: dict[str, Any]) -> Chunk:
    return Chunk(
        chunk_ix=data["chunk_ix"],
        text_id=data["text_id"],
        point_id=data["point_id"],
        status=ChunkStatus(data["status"]),
        attempts=data["attempts"],
    )


class IndexingJobMapper:
    """Преобразование между ``IndexingJobORM`` и ``IndexingJob``."""

    @staticmethod
    def to_orm(job: IndexingJob) -> IndexingJobORM:
        """Строит ORM-строку из доменной сущности."""
        return IndexingJobORM(
            job_id=job.job_id.value,
            product_id=job.product_id.value,
            sku=job.sku.value,
            aggregate_version=job.aggregate_version,
            content_version=job.content_version,
            content_hash=job.content_hash.value,
            action=job.action.value,
            target_collection=job.target_collection,
            expected_model=job.expected_model,
            status=job.status.value,
            chunks=[_chunk_to_dict(chunk) for chunk in job.chunks],
            created_at=job.created_at,
            updated_at=job.updated_at,
            applied_at=job.applied_at,
        )

    @staticmethod
    def to_domain(row: IndexingJobORM) -> IndexingJob:
        """Восстанавливает доменную сущность из строки БД."""
        return IndexingJob(
            job_id=JobId(row.job_id),
            product_id=ProductId(row.product_id),
            sku=Sku(row.sku),
            aggregate_version=row.aggregate_version,
            content_version=row.content_version,
            content_hash=ContentHash(row.content_hash),
            action=IndexAction(row.action),
            target_collection=row.target_collection,
            expected_model=row.expected_model,
            status=JobStatus(row.status),
            chunks=tuple(_chunk_from_dict(item) for item in row.chunks),
            created_at=row.created_at,
            updated_at=row.updated_at,
            applied_at=row.applied_at,
        )


class EmbeddingRequestMapper:
    """Преобразование между ``EmbeddingRequestORM`` и ``EmbeddingRequest``."""

    @staticmethod
    def to_orm(request: EmbeddingRequest) -> EmbeddingRequestORM:
        """Строит ORM-строку из доменной сущности."""
        return EmbeddingRequestORM(
            request_id=request.request_id.value,
            job_id=request.job_id.value,
            attempt=request.attempt,
            items=[
                {"text_id": item.text_id, "text": item.text}
                for item in request.items
            ],
            status=request.status.value,
            next_attempt_at=request.next_attempt_at,
            created_at=request.created_at,
            requested_at=request.requested_at,
            received_at=request.received_at,
        )

    @staticmethod
    def to_domain(row: EmbeddingRequestORM) -> EmbeddingRequest:
        """Восстанавливает доменную сущность из строки БД."""
        return EmbeddingRequest(
            request_id=RequestId(row.request_id),
            job_id=JobId(row.job_id),
            attempt=row.attempt,
            items=tuple(
                RequestItem(text_id=item["text_id"], text=item["text"])
                for item in row.items
            ),
            status=RequestStatus(row.status),
            next_attempt_at=row.next_attempt_at,
            created_at=row.created_at,
            requested_at=row.requested_at,
            received_at=row.received_at,
        )
