"""Unit-тесты SystemClock и UuidGenerator."""

from datetime import UTC

from embedding_service.infrastructure.services.clock import SystemClock
from embedding_service.infrastructure.services.id_generator import (
    UuidGenerator,
)


def test_clock_returns_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo == UTC


def test_uuid7_version_and_uniqueness() -> None:
    generator = UuidGenerator()
    first = generator.new_uuid7()
    second = generator.new_uuid7()
    assert first.version == 7
    assert first != second
