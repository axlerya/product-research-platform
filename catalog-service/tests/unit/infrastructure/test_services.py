"""Тесты инфраструктурных сервисов (часы, генератор id)."""

from catalog_service.infrastructure.services.clock import SystemClock
from catalog_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)


def test_clock_returns_utc():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0


def test_product_id_is_uuid7():
    assert Uuid7Generator().new_product_id().value.version == 7


def test_message_ids_are_unique_uuid7():
    gen = Uuid7Generator()
    first, second = gen.new_message_id(), gen.new_message_id()
    assert first.version == 7
    assert second.version == 7
    assert first != second
