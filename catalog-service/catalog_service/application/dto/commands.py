"""Команды и их результаты (входные/выходные DTO write-side).

Деньги — ``Decimal`` (никогда float). Идентификация обновлений — по
``product_id``; ``expected_version`` — оптимистичная блокировка.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateProductCommand:
    """Создание товара. Валюта берётся из настройки, если не задана."""

    sku: str
    name: str
    description: str
    category_name: str
    brand_name: str
    supplier_name: str
    price_amount: Decimal
    cost_amount: Decimal
    stock_quantity: int
    sales_per_month: int
    avg_rating: Decimal
    review_count: int
    source_updated_at: date | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProductContentCommand:
    """Частичное обновление контентных полей товара."""

    product_id: UUID
    expected_version: int
    name: str | None = None
    description: str | None = None
    category_name: str | None = None
    brand_name: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCommercialDataCommand:
    """Частичное обновление коммерческих данных товара."""

    product_id: UUID
    expected_version: int
    price_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    stock_quantity: int | None = None
    supplier_name: str | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class SetStockCommand:
    """Установка абсолютного значения остатка."""

    product_id: UUID
    expected_version: int
    stock_quantity: int


@dataclass(frozen=True, slots=True)
class UpdateMetricsCommand:
    """Полная замена товарных метрик (без события)."""

    product_id: UUID
    expected_version: int
    sales_per_month: int
    avg_rating: Decimal
    review_count: int


@dataclass(frozen=True, slots=True)
class DeleteProductCommand:
    """Мягкое удаление товара."""

    product_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Тонкий результат команды.

    Attributes:
        product_id: Идентификатор товара.
        sku: Артикул.
        version: Актуальная версия после команды.
        emitted_events: Routing keys эмитированных событий (для тестов
            и наблюдаемости).
    """

    product_id: UUID
    sku: str
    version: int
    emitted_events: tuple[str, ...]
