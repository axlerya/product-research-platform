"""Тесты сущности ``EmbeddingRequest``."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from indexing_service.domain.entities.embedding_request import (
    EmbeddingRequest,
    RequestItem,
)
from indexing_service.domain.exceptions import InvalidRequestError
from indexing_service.domain.value_objects.identifiers import JobId, RequestId
from indexing_service.domain.value_objects.job_status import RequestStatus

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _req(**over) -> EmbeddingRequest:
    fields = dict(
        request_id=RequestId(UUID(int=1)),
        job_id=JobId(UUID(int=2)),
        attempt=0,
        items=(RequestItem(text_id="t0", text="документ"),),
        status=RequestStatus.PENDING,
        next_attempt_at=None,
        created_at=NOW,
        requested_at=None,
        received_at=None,
    )
    fields.update(over)
    return EmbeddingRequest(**fields)


def test_valid_request():
    req = _req()
    assert req.attempt == 0
    assert req.items[0].text_id == "t0"


def test_rejects_negative_attempt():
    with pytest.raises(InvalidRequestError):
        _req(attempt=-1)


def test_rejects_empty_items():
    with pytest.raises(InvalidRequestError):
        _req(items=())


def test_rejects_empty_text_id():
    with pytest.raises(InvalidRequestError):
        RequestItem(text_id="", text="x")
