"""Реализация ``UnitOfWork`` поверх одной async-сессии SQLAlchemy.

Все репозитории делят одну ``AsyncSession``, поэтому job, команда и строка
outbox коммитятся атомарно одним ``commit()`` (transactional outbox).

Сессия живёт в ``ContextVar``, а не на экземпляре: консюмер держит один
экземпляр use case на все события, а обрабатывает их конкурентно
(подписчиков на очереди двое, prefetch больше единицы). Сессия на экземпляре
в таком режиме подменяется под работающей задачей — SQLAlchemy отвечает
``Session is already flushing``, событие уходит в ретрай-петлю, а задание
навсегда остаётся в ``pending``.
"""

from contextvars import ContextVar
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from indexing_service.infrastructure.db.repositories import (
    SqlAlchemyEmbeddingRequestRepository,
    SqlAlchemyIndexingJobRepository,
    SqlAlchemyOutboxRepository,
)


class SqlAlchemyUnitOfWork:
    """Единица работы: сессия + репозитории + outbox в одной транзакции."""

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker
        self._session: ContextVar[AsyncSession | None] = ContextVar(
            "indexing_uow_session", default=None
        )

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session.set(self._sessionmaker())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                await session.rollback()
        finally:
            await session.close()
            self._session.set(None)

    @property
    def jobs(self) -> SqlAlchemyIndexingJobRepository:
        """Репозиторий заданий на сессии текущей транзакции."""
        return SqlAlchemyIndexingJobRepository(self._require_session())

    @property
    def requests(self) -> SqlAlchemyEmbeddingRequestRepository:
        """Репозиторий команд на эмбеддинг на сессии текущей транзакции."""
        return SqlAlchemyEmbeddingRequestRepository(self._require_session())

    @property
    def outbox(self) -> SqlAlchemyOutboxRepository:
        """Репозиторий outbox на сессии текущей транзакции."""
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
