"""Тесты детерминированного ``request_id`` (§9.1)."""

from uuid import UUID

from indexing_service.application.request_id import deterministic_request_id
from indexing_service.domain.entities.embedding_request import RequestItem
from indexing_service.domain.value_objects.identifiers import JobId

_JOB = JobId(UUID(int=1))
_ITEMS = (
    RequestItem(text_id="c0", text="первый"),
    RequestItem(text_id="c1", text="второй"),
)


def test_is_deterministic_for_same_inputs():
    assert deterministic_request_id(
        _JOB, 0, _ITEMS
    ) == deterministic_request_id(_JOB, 0, _ITEMS)


def test_attempt_changes_id():
    assert deterministic_request_id(
        _JOB, 0, _ITEMS
    ) != deterministic_request_id(_JOB, 1, _ITEMS)


def test_items_change_id():
    other = (RequestItem(text_id="c0", text="другой текст"),)
    assert deterministic_request_id(
        _JOB, 0, _ITEMS
    ) != deterministic_request_id(_JOB, 0, other)


def test_job_changes_id():
    other_job = JobId(UUID(int=2))
    assert deterministic_request_id(
        _JOB, 0, _ITEMS
    ) != deterministic_request_id(other_job, 0, _ITEMS)


def test_is_uuid5():
    request_id = deterministic_request_id(_JOB, 0, _ITEMS)
    assert request_id.value.version == 5
