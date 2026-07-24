"""Тесты типобезопасных идентификаторов сущностей агента."""

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    FeedbackId,
    MessageId,
    ToolCallId,
)

ALL_ID_TYPES = [ConversationId, MessageId, AgentRunId, ToolCallId, FeedbackId]


@pytest.mark.parametrize("id_type", ALL_ID_TYPES)
def test_new_generates_uuid_version_7(id_type: type) -> None:
    """new() создаёт идентификатор с UUID версии 7."""
    identifier = id_type.new()

    assert isinstance(identifier.value, UUID)
    assert identifier.value.version == 7


@pytest.mark.parametrize("id_type", ALL_ID_TYPES)
def test_new_is_unique(id_type: type) -> None:
    """Два вызова new() дают разные идентификаторы."""
    assert id_type.new() != id_type.new()


def test_same_uuid_different_types_not_equal() -> None:
    """Идентификаторы разных типов не равны даже при одинаковом UUID."""
    shared = UUID(int=1)

    assert ConversationId(shared) != MessageId(shared)
    assert AgentRunId(shared) != ToolCallId(shared)


@pytest.mark.parametrize("id_type", ALL_ID_TYPES)
def test_identifier_is_frozen(id_type: type) -> None:
    """Идентификатор неизменяем после создания."""
    identifier = id_type.new()

    with pytest.raises(FrozenInstanceError):
        identifier.value = UUID(int=0)
