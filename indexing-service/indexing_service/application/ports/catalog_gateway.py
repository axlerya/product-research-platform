"""Порт ``CatalogGateway`` — REST-клиент к catalog-service.

Используется на горячем пути только для gap-repair; массово — для
reindex/reconcile (§14, тема 1).
"""

from collections.abc import AsyncIterator
from typing import Protocol

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.domain.value_objects.identifiers import ProductId


class CatalogGateway(Protocol):
    """Чтение актуального состояния товара из catalog-service."""

    async def get_product(
        self, product_id: ProductId
    ) -> ProductSnapshot | None:
        """Возвращает снимок товара или ``None``, если его нет."""
        ...

    def iter_products(
        self, *, batch: int = 100
    ) -> AsyncIterator[ProductSnapshot]:
        """Итерирует все товары каталога (keyset-пагинация)."""
        ...
