"""Read-side DTO (проекции для чтения, CQRS-lite)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MoneyView:
    """Деньги в проекции чтения."""

    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class MarginView:
    """Маржа в проекции чтения (percent = None при нулевой цене)."""

    profit: MoneyView
    percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ProductView:
    """Денормализованное представление товара для чтения."""

    id: UUID
    sku: str
    name: str
    description: str
    category: str
    brand: str
    supplier: str
    price: MoneyView
    cost: MoneyView
    stock: int
    is_in_stock: bool
    sales_per_month: int
    avg_rating: Decimal
    review_count: int
    margin: MarginView
    source_updated_at: date | None
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Page[T]:
    """Страница результатов (offset-пагинация)."""

    items: tuple[T, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class ReferenceView:
    """Элемент справочника с числом товаров."""

    id: UUID
    name: str
    product_count: int


@dataclass(frozen=True, slots=True)
class CategoryMarginRow:
    """Агрегат маржинальности по категории."""

    category: str
    product_count: int
    avg_margin_percent: Decimal | None
    min_margin_percent: Decimal | None
    max_margin_percent: Decimal | None
