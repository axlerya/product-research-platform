"""Use cases чтения истории запросов (ListQueries, GetQuery)."""

from research_agent_service.application.ports.uow import UnitOfWork
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.enums import RunStatus
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
)

_DEFAULT_LIMIT = 20


class ListQueriesUseCase:
    """Список прогонов с фильтрами и пагинацией."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self,
        *,
        conversation_id: ConversationId | None = None,
        status: RunStatus | None = None,
        limit: int = _DEFAULT_LIMIT,
        offset: int = 0,
    ) -> tuple[AgentRun, ...]:
        """Возвращает страницу прогонов."""
        async with self._uow as uow:
            return await uow.agent_runs.list(
                conversation_id=conversation_id,
                status=status,
                limit=limit,
                offset=offset,
            )


class GetQueryUseCase:
    """Детали одного прогона."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, run_id: AgentRunId) -> AgentRun | None:
        """Возвращает прогон по id (или None)."""
        async with self._uow as uow:
            return await uow.agent_runs.get(run_id)
