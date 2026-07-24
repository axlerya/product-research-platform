"""Тесты Uuid7Generator."""

from research_agent_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)


def test_generates_uuid_version_7() -> None:
    """Генератор выдаёт UUID версии 7."""
    assert Uuid7Generator().new_uuid7().version == 7


def test_generates_unique_values() -> None:
    """Два вызова дают разные идентификаторы."""
    generator = Uuid7Generator()

    assert generator.new_uuid7() != generator.new_uuid7()
