"""Тесты идентификаторов job/request."""

from uuid import UUID

from indexing_service.domain.value_objects.identifiers import JobId, RequestId


def test_job_id_new_is_uuid7():
    assert JobId.new().value.version == 7


def test_request_id_wraps_uuid():
    value = UUID(int=5)
    assert RequestId(value).value == value


def test_ids_equal_by_value():
    value = UUID(int=7)
    assert JobId(value) == JobId(value)
