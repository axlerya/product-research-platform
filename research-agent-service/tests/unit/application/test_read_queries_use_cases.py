"""Тесты use cases чтения истории (ListQueries, GetQuery)."""

from datetime import UTC, datetime
from uuid import UUID

from research_agent_service.application.use_cases.read_queries import (
    GetQueryUseCase,
    ListQueriesUseCase,
)
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)
from tests.support.fakes import FakeUnitOfWork


def _run() -> AgentRun:
    return AgentRun(
        id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        query_message_id=MessageId(UUID(int=3)),
        model="claude-opus-4-8",
        prompt_version="v1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_list_returns_runs() -> None:
    """ListQueries делегирует чтение репозиторию прогонов."""
    uow = FakeUnitOfWork()
    run = _run()
    uow.agent_runs.added.append(run)

    result = await ListQueriesUseCase(uow=uow).execute()

    assert result == (run,)


async def test_get_returns_run() -> None:
    """GetQuery возвращает прогон по id."""
    run = _run()
    uow = FakeUnitOfWork(run=run)

    result = await GetQueryUseCase(uow=uow).execute(run.id)

    assert result is run


async def test_get_returns_none_when_absent() -> None:
    """GetQuery возвращает None для отсутствующего прогона."""
    uow = FakeUnitOfWork(run=None)

    result = await GetQueryUseCase(uow=uow).execute(AgentRunId(UUID(int=9)))

    assert result is None
