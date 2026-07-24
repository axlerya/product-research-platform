"""Тесты сущности Conversation."""

from datetime import UTC, datetime

from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.value_objects.identifiers import (
    ConversationId,
)

_CREATED = datetime(2026, 1, 1, tzinfo=UTC)
_LATER = datetime(2026, 1, 2, tzinfo=UTC)


def test_new_conversation_starts_empty() -> None:
    """Новый диалог: 0 сообщений, updated_at == created_at, без заголовка."""
    conversation = Conversation(id=ConversationId.new(), created_at=_CREATED)

    assert conversation.message_count == 0
    assert conversation.updated_at == _CREATED
    assert conversation.title is None


def test_record_message_increments_count_and_touches() -> None:
    """record_message увеличивает счётчик и обновляет updated_at."""
    conversation = Conversation(id=ConversationId.new(), created_at=_CREATED)

    conversation.record_message(now=_LATER)

    assert conversation.message_count == 1
    assert conversation.updated_at == _LATER


def test_reconstructed_conversation_keeps_state() -> None:
    """Восстановление из хранилища сохраняет счётчик и метку обновления."""
    conversation = Conversation(
        id=ConversationId.new(),
        created_at=_CREATED,
        title="Поиск наушников",
        message_count=4,
        updated_at=_LATER,
    )

    assert conversation.title == "Поиск наушников"
    assert conversation.message_count == 4
    assert conversation.updated_at == _LATER
