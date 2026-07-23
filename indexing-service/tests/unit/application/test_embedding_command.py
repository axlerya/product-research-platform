"""Тесты сборки команды ``embedding.documents.requested.v1``."""

from datetime import UTC, datetime
from uuid import UUID

from indexing_service.application.embedding_command import (
    AGGREGATE_TYPE,
    EVENT_TYPE,
    EVENT_VERSION,
    PRODUCER,
    build_command_data,
    build_command_message,
)
from indexing_service.domain.entities.embedding_request import (
    EmbeddingRequest,
    RequestItem,
)
from indexing_service.domain.value_objects.identifiers import JobId, RequestId
from indexing_service.domain.value_objects.job_status import RequestStatus

_NOW = datetime(2026, 7, 20, 10, 15, 30, tzinfo=UTC)
_MESSAGE_ID = UUID(int=0xABC)


def _request() -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id=RequestId(UUID(int=0xDEF)),
        job_id=JobId(UUID(int=1)),
        attempt=0,
        items=(
            RequestItem(text_id="p1::0", text="первый"),
            RequestItem(text_id="p1::1", text="второй"),
        ),
        status=RequestStatus.PENDING,
        next_attempt_at=None,
        created_at=_NOW,
        requested_at=None,
        received_at=None,
    )


def test_data_carries_items_in_order_and_flags():
    data = build_command_data(_request(), model="BAAI/bge-m3")
    assert data["request_id"] == str(UUID(int=0xDEF))
    assert data["return_dense"] is True
    assert data["return_sparse"] is True
    assert data["model"] == "BAAI/bge-m3"
    assert [item["text_id"] for item in data["items"]] == ["p1::0", "p1::1"]
    assert data["items"][0]["text"] == "первый"


def test_data_omits_model_when_none():
    data = build_command_data(_request(), model=None)
    assert "model" not in data


def test_data_honours_return_flags():
    data = build_command_data(
        _request(), model=None, return_dense=True, return_sparse=False
    )
    assert data["return_dense"] is True
    assert data["return_sparse"] is False


def test_message_wraps_envelope_and_correlates_by_request_id():
    request = _request()
    message = build_command_message(
        request, model="BAAI/bge-m3", message_id=_MESSAGE_ID, occurred_at=_NOW
    )
    assert message.id == _MESSAGE_ID
    assert message.event_type == EVENT_TYPE
    assert message.aggregate_id == request.request_id.value
    assert message.aggregate_type == "embedding_request"

    envelope = message.payload
    assert envelope["event_id"] == str(_MESSAGE_ID)
    assert envelope["event_type"] == EVENT_TYPE
    assert envelope["event_version"] == EVENT_VERSION
    assert envelope["aggregate_type"] == AGGREGATE_TYPE
    assert envelope["aggregate_id"] == str(request.request_id.value)
    assert envelope["producer"] == PRODUCER
    assert envelope["occurred_at"] == _NOW.isoformat()
    assert "trace_id" not in envelope


def test_message_includes_trace_id_when_given():
    message = build_command_message(
        _request(),
        model=None,
        message_id=_MESSAGE_ID,
        occurred_at=_NOW,
        trace_id="00-abc-def-01",
    )
    assert message.payload["trace_id"] == "00-abc-def-01"
    assert message.headers == {"trace_id": "00-abc-def-01"}


def test_message_is_publishable_immediately_by_default():
    message = build_command_message(
        _request(), model=None, message_id=_MESSAGE_ID, occurred_at=_NOW
    )
    assert message.next_attempt_at is None


def test_message_carries_delayed_publication():
    due = datetime(2026, 7, 20, 10, 20, tzinfo=UTC)
    message = build_command_message(
        _request(),
        model=None,
        message_id=_MESSAGE_ID,
        occurred_at=_NOW,
        next_attempt_at=due,
    )
    # backoff живёт в строке outbox, а не в конверте команды
    assert message.next_attempt_at == due
    assert "next_attempt_at" not in message.payload
