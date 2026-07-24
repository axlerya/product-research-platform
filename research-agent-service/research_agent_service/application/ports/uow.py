"""Порт UnitOfWork — атомарная транзакция с репозиториями и outbox."""

from types import TracebackType
from typing import Protocol, Self

from research_agent_service.application.ports.outbox import OutboxRepository
from research_agent_service.application.ports.repositories import (
    AgentRunRepository,
    ConversationRepository,
    FeedbackRepository,
)


class UnitOfWork(Protocol):
    """Единица работы: репозитории на одной сессии, один commit()."""

    conversations: ConversationRepository
    agent_runs: AgentRunRepository
    feedback: FeedbackRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> Self:
        """Открывает транзакцию."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает транзакцию (rollback при исключении)."""
        ...

    async def commit(self) -> None:
        """Фиксирует изменения."""
        ...

    async def rollback(self) -> None:
        """Откатывает изменения."""
        ...
