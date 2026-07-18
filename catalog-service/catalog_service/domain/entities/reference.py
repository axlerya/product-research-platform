"""Справочные сущности: ``Category`` / ``Brand`` / ``Supplier``."""

from dataclasses import dataclass
from datetime import datetime

from catalog_service.domain.value_objects.identifiers import (
    BrandId,
    CategoryId,
    SupplierId,
)


@dataclass(frozen=True, slots=True)
class Category:
    """Категория товаров (справочник).

    Attributes:
        id: Идентификатор категории.
        name: Уникальное имя (натуральный ключ).
        created_at: Момент создания.
    """

    id: CategoryId
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Brand:
    """Бренд (справочник)."""

    id: BrandId
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Supplier:
    """Поставщик (справочник)."""

    id: SupplierId
    name: str
    created_at: datetime
