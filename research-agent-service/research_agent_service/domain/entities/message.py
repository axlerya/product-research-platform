"""Сущность Message — реплика в диалоге."""

from dataclasses import dataclass
from datetime import datetime

from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import MessageRole
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)


@dataclass(frozen=True, slots=True)
class Message:
    """Реплика диалога (иммутабельна после создания).

    Attributes:
        id: Идентификатор сообщения.
        conversation_id: Диалог, которому принадлежит сообщение.
        role: Роль автора реплики.
        content: Текст реплики.
        created_at: Момент создания.
        agent_run_id: Прогон агента (для ответа ассистента).
        citations: Источники факта (для ответа ассистента).
        token_count: Число токенов, если известно.
    """

    id: MessageId
    conversation_id: ConversationId
    role: MessageRole
    content: str
    created_at: datetime
    agent_run_id: AgentRunId | None = None
    citations: tuple[Citation, ...] = ()
    token_count: int | None = None
