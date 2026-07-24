"""Порты репозиториев — персистентность агрегатов агента."""

from typing import Protocol

from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.value_objects.enums import RunStatus
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)


class ConversationRepository(Protocol):
    """Диалоги и их сообщения."""

    async def add(self, conversation: Conversation) -> None:
        """Сохраняет новый диалог."""
        ...

    async def get(self, conversation_id: ConversationId) -> Conversation | None:
        """Возвращает диалог по id (или None)."""
        ...

    async def add_message(self, message: Message) -> None:
        """Добавляет сообщение в диалог."""
        ...

    async def get_message(self, message_id: MessageId) -> Message | None:
        """Возвращает сообщение по id (или None)."""
        ...

    async def load_history(
        self, conversation_id: ConversationId, *, limit: int
    ) -> tuple[Message, ...]:
        """Возвращает последние сообщения диалога."""
        ...


class AgentRunRepository(Protocol):
    """Прогоны агента и их вызовы инструментов."""

    async def add(self, run: AgentRun) -> None:
        """Сохраняет прогон вместе с его вызовами инструментов."""
        ...

    async def get(self, run_id: AgentRunId) -> AgentRun | None:
        """Возвращает прогон по id (или None)."""
        ...

    async def list(
        self,
        *,
        conversation_id: ConversationId | None = None,
        status: RunStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[AgentRun, ...]:
        """Список прогонов с фильтрами и пагинацией."""
        ...


class FeedbackRepository(Protocol):
    """Обратная связь по прогонам."""

    async def add(self, feedback: Feedback) -> None:
        """Сохраняет обратную связь."""
        ...
