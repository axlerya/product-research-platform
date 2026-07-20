"""Реализация ``UnitOfWork`` поверх одной async-сессии SQLAlchemy.

Все репозитории делят одну ``AsyncSession``, поэтому job, команда и строка
outbox коммитятся атомарно одним ``commit()`` (transactional outbox).
"""

from types import TracebackType

from sqlalchemy.ext.asyncio import async_sessionmaker

from indexing_service.infrastructure.db.repositories import (
    SqlAlchemyEmbeddingRequestRepository,
    SqlAlchemyIndexingJobRepository,
    SqlAlchemyOutboxRepository,
)


class SqlAlchemyUnitOfWork:
    """Единица работы: сессия + репозитории + outbox в одной транзакции."""

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._sessionmaker()
        self.jobs = SqlAlchemyIndexingJobRepository(self._session)
        self.requests = SqlAlchemyEmbeddingRequestRepository(self._session)
        self.outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
