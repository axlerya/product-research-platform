"""Порты репозиториев (write-side)."""

from typing import Protocol

from catalog_service.domain.entities.product import Product
from catalog_service.domain.entities.reference import (
    Brand,
    Category,
    Supplier,
)
from catalog_service.domain.value_objects.identifiers import ProductId
from catalog_service.domain.value_objects.sku import Sku


class ProductRepository(Protocol):
    """Хранилище агрегата ``Product`` с оптимистичной блокировкой."""

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        """Возвращает товар по идентификатору или ``None``."""
        ...

    async def get_by_sku(self, sku: Sku) -> Product | None:
        """Возвращает товар по артикулу или ``None``."""
        ...

    async def add(self, product: Product) -> None:
        """Добавляет новый товар."""
        ...

    async def update(self, product: Product, *, expected_version: int) -> None:
        """Обновляет товар при совпадении версии.

        Args:
            product: Изменённый агрегат (версия уже увеличена доменом).
            expected_version: Ожидаемая версия в хранилище.

        Raises:
            ConcurrencyConflict: Если версия в хранилище не совпала.
        """
        ...


class CategoryRepository(Protocol):
    """Справочник категорий (идемпотентный get-or-create)."""

    async def get_or_create(self, name: str) -> Category:
        """Возвращает существующую категорию или создаёт новую."""
        ...


class BrandRepository(Protocol):
    """Справочник брендов (идемпотентный get-or-create)."""

    async def get_or_create(self, name: str) -> Brand:
        """Возвращает существующий бренд или создаёт новый."""
        ...


class SupplierRepository(Protocol):
    """Справочник поставщиков (идемпотентный get-or-create)."""

    async def get_or_create(self, name: str) -> Supplier:
        """Возвращает существующего поставщика или создаёт нового."""
        ...
