"""Реализация ``UnitOfWork`` поверх одной async-сессии SQLAlchemy.

Все репозитории делят одну ``AsyncSession``, поэтому мутация агрегата и
строки outbox коммитятся атомарно одним ``commit()``.
"""

from types import TracebackType

from sqlalchemy.ext.asyncio import async_sessionmaker

from catalog_service.infrastructure.db.repositories import (
    SqlAlchemyBrandRepository,
    SqlAlchemyCategoryRepository,
    SqlAlchemyOutboxRepository,
    SqlAlchemyProductRepository,
    SqlAlchemySupplierRepository,
)


class SqlAlchemyUnitOfWork:
    """Единица работы: сессия + репозитории + outbox в одной транзакции."""

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._sessionmaker()
        self.products = SqlAlchemyProductRepository(self._session)
        self.categories = SqlAlchemyCategoryRepository(self._session)
        self.brands = SqlAlchemyBrandRepository(self._session)
        self.suppliers = SqlAlchemySupplierRepository(self._session)
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
