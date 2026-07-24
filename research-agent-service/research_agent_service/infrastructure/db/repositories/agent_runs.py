"""SQLAlchemy-репозиторий прогонов агента и их вызовов."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.enums import RunStatus
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
)
from research_agent_service.infrastructure.db.mappers import (
    agent_run_from_orm,
    agent_run_to_orm,
    tool_call_to_orm,
)
from research_agent_service.infrastructure.db.models import (
    AgentRunORM,
    ToolCallORM,
)


class SqlAlchemyAgentRunRepository:
    """Прогоны и их вызовы инструментов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: AgentRun) -> None:
        self._session.add(agent_run_to_orm(run))
        for call in run.tool_calls:
            self._session.add(tool_call_to_orm(call))

    async def get(self, run_id: AgentRunId) -> AgentRun | None:
        orm = await self._session.get(AgentRunORM, run_id.value)
        if orm is None:
            return None
        return await self._load(orm)

    async def list(
        self,
        *,
        conversation_id: ConversationId | None = None,
        status: RunStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[AgentRun, ...]:
        stmt = select(AgentRunORM)
        if conversation_id is not None:
            stmt = stmt.where(
                AgentRunORM.conversation_id == conversation_id.value
            )
        if status is not None:
            stmt = stmt.where(AgentRunORM.status == status.value)
        stmt = (
            stmt.order_by(AgentRunORM.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return tuple([await self._load(row) for row in rows])

    async def _load(self, orm: AgentRunORM) -> AgentRun:
        stmt = (
            select(ToolCallORM)
            .where(ToolCallORM.agent_run_id == orm.id)
            .order_by(ToolCallORM.step_index)
        )
        tool_calls = (await self._session.scalars(stmt)).all()
        return agent_run_from_orm(orm, tool_calls)
