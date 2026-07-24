"""Тесты сборки стартовых сообщений агента."""

from datetime import UTC, datetime
from uuid import UUID

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.value_objects.enums import MessageRole
from research_agent_service.domain.value_objects.identifiers import (
    ConversationId,
    MessageId,
)
from research_agent_service.domain.value_objects.query import Query
from research_agent_service.infrastructure.agent.prompts import build_messages

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _msg(role: MessageRole, content: str) -> Message:
    return Message(
        id=MessageId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        role=role,
        content=content,
        created_at=_NOW,
    )


def test_build_messages_starts_with_system_and_ends_with_query() -> None:
    """Первое сообщение — системный промпт, последнее — запрос пользователя."""
    messages = build_messages(Query(text="вопрос"), ())

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[-1], HumanMessage)
    assert messages[-1].content == "вопрос"
    assert len(messages) == 2


def test_build_messages_maps_history_and_skips_non_dialogue() -> None:
    """История USER/ASSISTANT переносится; прочие роли пропускаются."""
    history = (
        _msg(MessageRole.USER, "привет"),
        _msg(MessageRole.ASSISTANT, "здравствуйте"),
        _msg(MessageRole.SYSTEM, "внутреннее"),
    )

    messages = build_messages(Query(text="вопрос"), history)

    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "привет"
    assert isinstance(messages[2], AIMessage)
    assert messages[2].content == "здравствуйте"
    contents = [m.content for m in messages]
    assert "внутреннее" not in contents
    # система + 2 реплики + запрос
    assert len(messages) == 4
