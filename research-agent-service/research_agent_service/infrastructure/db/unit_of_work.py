"""SqlAlchemyUnitOfWork — атомарная транзакция с репозиториями."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from research_agent_service.infrastructure.db.repositories.agent_runs import (
    SqlAlchemyAgentRunRepository,
)
from research_agent_service.infrastructure.db.repositories.conversations import (  # noqa: E501
    SqlAlchemyConversationRepository,
)
from research_agent_service.infrastructure.db.repositories.feedback import (
    SqlAlchemyFeedbackRepository,
)
from research_agent_service.infrastructure.db.repositories.outbox import (
    SqlAlchemyOutboxRepository,
)


class SqlAlchemyUnitOfWork:
    """Единица работы: репозитории на одной сессии, один commit()."""

    def __init__(
        self, *, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        session = self._session_factory()
        self._session = session
        self.conversations = SqlAlchemyConversationRepository(session)
        self.agent_runs = SqlAlchemyAgentRunRepository(session)
        self.feedback = SqlAlchemyFeedbackRepository(session)
        self.outbox = SqlAlchemyOutboxRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork не открыт")
        return self._session
