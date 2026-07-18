"""Доменные события товара.

Ровно 4 типа: создание, изменение контента, изменение коммерческих
данных, удаление. Изменение метрик события НЕ порождает (см. агрегат).
Полное тело события (envelope) собирается на слое outbox из доменного
события и текущего состояния товара.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from catalog_service.domain.value_objects.identifiers import ProductId


class DomainEvent:
    """Маркерный базовый класс доменного события.

    Attributes:
        routing_key: Ключ маршрутизации события (задаётся подклассом).
    """

    __slots__ = ()
    routing_key: ClassVar[str]


@dataclass(frozen=True, slots=True)
class ProductCreated(DomainEvent):
    """Товар создан."""

    product_id: ProductId
    occurred_at: datetime
    routing_key: ClassVar[str] = "catalog.product.created"


@dataclass(frozen=True, slots=True)
class ProductContentChanged(DomainEvent):
    """Изменён контент товара (name/description/category/brand)."""

    product_id: ProductId
    changed_fields: tuple[str, ...]
    occurred_at: datetime
    routing_key: ClassVar[str] = "catalog.product.content_changed"


@dataclass(frozen=True, slots=True)
class ProductCommercialDataChanged(DomainEvent):
    """Изменены коммерческие данные (price/cost/stock/supplier)."""

    product_id: ProductId
    changed_fields: tuple[str, ...]
    occurred_at: datetime
    routing_key: ClassVar[str] = "catalog.product.commercial_data_changed"


@dataclass(frozen=True, slots=True)
class ProductDeleted(DomainEvent):
    """Товар удалён (soft-delete)."""

    product_id: ProductId
    occurred_at: datetime
    routing_key: ClassVar[str] = "catalog.product.deleted"
