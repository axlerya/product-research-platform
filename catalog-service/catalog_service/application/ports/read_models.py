"""Порты read-side (CQRS-lite): сервисы запросов."""

from typing import Protocol
from uuid import UUID

from catalog_service.application.dto.queries import ProductSearchQuery
from catalog_service.application.dto.views import (
    CategoryMarginRow,
    Page,
    ProductView,
    ReferenceView,
)


class ProductQueryService(Protocol):
    """Чтение товаров без гидрации доменного агрегата."""

    async def get(
        self,
        *,
        product_id: UUID | None = None,
        sku: str | None = None,
        include_deleted: bool = False,
    ) -> ProductView | None:
        """Возвращает товар по id или sku (или ``None``)."""
        ...

    async def search(self, query: ProductSearchQuery) -> Page[ProductView]:
        """Ищет товары по фильтрам с пагинацией."""
        ...

    async def margin_by_category(
        self, *, include_deleted: bool = False
    ) -> tuple[CategoryMarginRow, ...]:
        """Агрегат маржинальности по категориям."""
        ...


class ReferenceQueryService(Protocol):
    """Чтение справочников с числом товаров."""

    async def list_categories(self) -> tuple[ReferenceView, ...]:
        """Список категорий."""
        ...

    async def list_brands(self) -> tuple[ReferenceView, ...]:
        """Список брендов."""
        ...

    async def list_suppliers(self) -> tuple[ReferenceView, ...]:
        """Список поставщиков."""
        ...
