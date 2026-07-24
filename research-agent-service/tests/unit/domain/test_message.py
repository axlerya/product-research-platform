"""Тесты сущности Message."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.value_objects.enums import MessageRole
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_message_holds_fields_and_defaults() -> None:
    """Обязательные поля сохраняются; необязательные — по умолчанию."""
    message = Message(
        id=MessageId.new(),
        conversation_id=ConversationId.new(),
        role=MessageRole.USER,
        content="найди наушники",
        created_at=_NOW,
    )

    assert message.role is MessageRole.USER
    assert message.content == "найди наушники"
    assert message.agent_run_id is None
    assert message.citations == ()
    assert message.token_count is None


def test_assistant_message_carries_run_and_citations() -> None:
    """Ответ ассистента ссылается на прогон и несёт источники."""
    run_id = AgentRunId.new()
    message = Message(
        id=MessageId.new(),
        conversation_id=ConversationId.new(),
        role=MessageRole.ASSISTANT,
        content="вот варианты",
        created_at=_NOW,
        agent_run_id=run_id,
        token_count=42,
    )

    assert message.agent_run_id == run_id
    assert message.token_count == 42


def test_message_is_frozen() -> None:
    """Message неизменяемо после создания."""
    message = Message(
        id=MessageId.new(),
        conversation_id=ConversationId.new(),
        role=MessageRole.SYSTEM,
        content="системная реплика",
        created_at=_NOW,
    )

    with pytest.raises(FrozenInstanceError):
        message.content = "другое"
