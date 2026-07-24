"""SqlAlchemyUnitOfWork — атомарная транзакция с репозиториями.

Сессия хранится в ContextVar, а не на экземпляре: один UnitOfWork безопасно
делится между конкурентными запросами (каждая async-задача видит свою
сессию). Репозитории — свойства, привязанные к сессии текущего контекста.
"""

from contextvars import ContextVar
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
        self._session: ContextVar[AsyncSession | None] = ContextVar(
            "uow_session", default=None
        )

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session.set(self._session_factory())
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
            self._session.set(None)

    @property
    def conversations(self) -> SqlAlchemyConversationRepository:
        return SqlAlchemyConversationRepository(self._require_session())

    @property
    def agent_runs(self) -> SqlAlchemyAgentRunRepository:
        return SqlAlchemyAgentRunRepository(self._require_session())

    @property
    def feedback(self) -> SqlAlchemyFeedbackRepository:
        return SqlAlchemyFeedbackRepository(self._require_session())

    @property
    def outbox(self) -> SqlAlchemyOutboxRepository:
        return SqlAlchemyOutboxRepository(self._require_session())

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        session = self._session.get()
        if session is None:
            raise RuntimeError("UnitOfWork не открыт")
        return session
