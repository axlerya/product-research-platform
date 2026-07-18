"""Порт Unit of Work — транзакционная граница write-side."""

from types import TracebackType
from typing import Protocol

from catalog_service.application.ports.outbox import OutboxRepository
from catalog_service.application.ports.repositories import (
    BrandRepository,
    CategoryRepository,
    ProductRepository,
    SupplierRepository,
)


class UnitOfWork(Protocol):
    """Единица работы: репозитории + outbox в одной транзакции.

    Мутация агрегата и строки outbox коммитятся атомарно одним
    ``commit()``.
    """

    products: ProductRepository
    categories: CategoryRepository
    brands: BrandRepository
    suppliers: SupplierRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> "UnitOfWork":
        """Открывает транзакцию."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Откатывает транзакцию при исключении."""
        ...

    async def commit(self) -> None:
        """Фиксирует транзакцию."""
        ...

    async def rollback(self) -> None:
        """Откатывает транзакцию."""
        ...
