"""Сущность Feedback — обратная связь по прогону."""

from dataclasses import dataclass
from datetime import datetime

from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    FeedbackId,
)


@dataclass(frozen=True, slots=True)
class Feedback:
    """Обратная связь пользователя по прогону агента.

    Attributes:
        id: Идентификатор обратной связи.
        agent_run_id: Прогон, к которому относится оценка.
        conversation_id: Диалог прогона.
        rating: Оценка (up/down).
        created_at: Момент получения.
        reason: Свободная причина (для негативной оценки).
        labels: Метки-теги причины.
    """

    id: FeedbackId
    agent_run_id: AgentRunId
    conversation_id: ConversationId
    rating: FeedbackRating
    created_at: datetime
    reason: str | None = None
    labels: tuple[str, ...] = ()
