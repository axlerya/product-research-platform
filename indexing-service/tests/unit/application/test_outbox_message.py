"""Тест DTO ``OutboxMessage`` и импортируемости портов хранилища."""

from datetime import UTC, datetime
from uuid import UUID

from indexing_service.application.outbox_message import OutboxMessage
from indexing_service.application.ports.job_store import (
    EmbeddingRequestRepository,
    IndexingJobRepository,
)
from indexing_service.application.ports.outbox import OutboxRepository
from indexing_service.application.ports.unit_of_work import UnitOfWork


def test_outbox_message_holds_command_envelope():
    message = OutboxMessage(
        id=UUID(int=1),
        aggregate_type="embedding_request",
        aggregate_id=UUID(int=2),
        event_type="embedding.documents.requested.v1",
        payload={"data": {"request_id": "..."}},
        occurred_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    assert message.event_type == "embedding.documents.requested.v1"
    assert message.headers == {}


def test_ports_importable():
    ports = (
        IndexingJobRepository,
        EmbeddingRequestRepository,
        OutboxRepository,
        UnitOfWork,
    )
    assert all(hasattr(port, "__mro__") for port in ports)
