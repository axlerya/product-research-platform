"""Тесты типобезопасного идентификатора ``ProductId`` (uuidv7)."""

from uuid import UUID

from indexing_service.domain.value_objects.identifiers import ProductId

_SAMPLE = UUID("0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a")


def test_new_is_uuid_version_7():
    assert ProductId.new().value.version == 7


def test_new_ids_differ():
    assert ProductId.new() != ProductId.new()


def test_equality_by_value():
    assert ProductId(_SAMPLE) == ProductId(_SAMPLE)


def test_wraps_uuid():
    assert ProductId(_SAMPLE).value == _SAMPLE
