"""Порты read-side (CQRS-lite): сервисы запросов."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from catalog_service.application.dto.queries import (
    PriceAnalysisSelector,
    ProductSearchQuery,
)
from catalog_service.application.dto.views import (
    CategoryMarginRow,
    Page,
    ProductBatchView,
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

    async def get_many(
        self, skus: Sequence[str], *, include_deleted: bool = False
    ) -> ProductBatchView:
        """Читает товары пачкой по артикулам, отмечая отсутствующие."""
        ...

    async def search(self, query: ProductSearchQuery) -> Page[ProductView]:
        """Ищет товары по фильтрам с пагинацией."""
        ...

    async def select_for_analysis(
        self, selector: PriceAnalysisSelector
    ) -> tuple[ProductView, ...]:
        """Отбирает срез товаров для ценового анализа (без пагинации)."""
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
