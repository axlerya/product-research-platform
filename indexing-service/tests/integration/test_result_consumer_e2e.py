"""E2E: событие generated.v1 → консюмер → Postgres + Qdrant (§6, §11).

Реальные RabbitMQ + Postgres + Qdrant. Фейк embedding-service публикует
результат в ``embedding.events``; наш dispatch применяет его через
``ApplyEmbeddingResult``: job → DONE, точка чанка в Qdrant.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from faststream import AckPolicy
from faststream.rabbit import RabbitBroker, RabbitMessage, TestRabbitBroker

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
    IndexAction,
    JobStatus,
    RequestStatus,
)
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.embedding_sink import (
    QdrantEmbeddingSink,
)
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)
from indexing_service.presentation.messaging.embedding_topology import (
    EMBEDDING_EVENTS,
    ROUTING_KEY,
    result_main_queue,
)
from indexing_service.presentation.messaging.result_dispatch import (
    dispatch_result,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_JOB_ID = JobId(uuid4())
_REQ_ID = RequestId(uuid4())
_PRODUCT = ProductId(uuid4())
_POINT_ID = str(uuid4())


class _Clock:
    def now(self):
        return _NOW


def _job() -> IndexingJob:
    return IndexingJob(
        job_id=_JOB_ID,
        product_id=_PRODUCT,
        sku=Sku("PROD-1"),
        aggregate_version=2,
        content_version=3,
        content_hash=ContentHash.of("t"),
        action=IndexAction.FULL_INDEX,
        target_collection=None,
        expected_model="m",
        status=JobStatus.AWAITING,
        chunks=(
            Chunk(
                chunk_ix=0,
                text_id="c0",
                point_id=_POINT_ID,
                status=ChunkStatus.PENDING,
                attempts=0,
            ),
        ),
        created_at=_NOW,
        updated_at=_NOW,
        applied_at=None,
    )


def _request() -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id=_REQ_ID,
        job_id=_JOB_ID,
        attempt=0,
        items=(RequestItem(text_id="c0", text="текст"),),
        status=RequestStatus.AWAITING,
        next_attempt_at=None,
        created_at=_NOW,
        requested_at=_NOW,
        received_at=None,
    )


def _generated_envelope() -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": "embedding.documents.generated.v1",
        "event_version": "1.0",
        "aggregate_type": "embedding_job",
        "aggregate_id": str(_REQ_ID.value),
        "occurred_at": _NOW.isoformat(),
        "producer": "embedding-service",
        "data": {
            "request_id": str(_REQ_ID.value),
            "model_version": "m",
            "dim": 4,
            "results": [
                {
                    "text_id": "c0",
                    "status": "ok",
                    "dense": [0.1, 0.2, 0.3, 0.4],
                    "sparse": {"indices": [1, 3], "values": [0.5, 0.2]},
                    "token_count": 5,
                }
            ],
        },
    }


async def test_generated_event_applies_to_qdrant_and_marks_done(
    sessionmaker_, qdrant_client, rabbitmq_url
):
    collection = f"chunks_e2e_{uuid4().hex[:8]}"
    await CollectionProvisioner(
        qdrant_client, collection=collection, dim=4
    ).ensure()

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.jobs.upsert(_job())
        await uow.requests.add(_request())
        await uow.commit()

    use_case = ApplyEmbeddingResult(
        SqlAlchemyUnitOfWork(sessionmaker_),
        QdrantEmbeddingSink(qdrant_client, default_collection=collection),
        _Clock(),
        expected_dim=4,
        max_item_attempts=5,
    )
    parked: list = []

    async def _park(message) -> None:
        parked.append(message)

    broker = RabbitBroker(rabbitmq_url)

    @broker.subscriber(
        result_main_queue(), EMBEDDING_EVENTS, ack_policy=AckPolicy.MANUAL
    )
    async def handler(
        envelope: EmbeddingEventEnvelope, message: RabbitMessage
    ) -> None:
        await dispatch_result(
            envelope,
            message,
            use_case=use_case,
            park=_park,
            max_attempts=5,
        )

    async with TestRabbitBroker(broker, with_real=True):
        await broker.publish(
            _generated_envelope(),
            exchange=EMBEDDING_EVENTS,
            routing_key=ROUTING_KEY,
        )
        await handler.wait_call(timeout=10)

    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        job = await uow.jobs.get(_JOB_ID)
        request = await uow.requests.get(_REQ_ID)
    assert job.status is JobStatus.DONE
    assert request.status is RequestStatus.DONE
    assert parked == []

    records = await qdrant_client.retrieve(
        collection_name=collection,
        ids=[_POINT_ID],
        with_payload=True,
        with_vectors=True,
    )
    assert records[0].payload["content_version"] == 3
    assert records[0].payload["aggregate_version"] == 2
    assert "dense" in records[0].vector
