"""Тесты типобезопасных идентификаторов (uuidv7)."""

from uuid import UUID

from catalog_service.domain.value_objects.identifiers import (
    CategoryId,
    ProductId,
)


def test_new_generates_uuid7():
    pid = ProductId.new()
    assert isinstance(pid.value, UUID)
    assert pid.value.version == 7


def test_new_ids_are_unique():
    assert ProductId.new() != ProductId.new()


def test_wraps_existing_uuid():
    raw = UUID(int=42)
    assert ProductId(raw).value == raw


def test_equality_within_type():
    raw = UUID(int=42)
    assert ProductId(raw) == ProductId(raw)


def test_distinct_types_not_equal():
    raw = UUID(int=42)
    assert ProductId(raw) != CategoryId(raw)
