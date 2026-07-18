"""Схемы ответов чтения (из application-DTO ``*View``)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from catalog_service.presentation.api.schemas.common import (
    Amount,
    PercentOpt,
    RatingValue,
)


class MoneyRead(BaseModel):
    """Деньги в ответе (сумма строкой + валюта)."""

    model_config = ConfigDict(from_attributes=True)
    amount: Amount
    currency: str


class MarginRead(BaseModel):
    """Маржа в ответе."""

    model_config = ConfigDict(from_attributes=True)
    profit: MoneyRead
    percent: PercentOpt


class ProductRead(BaseModel):
    """Полное представление товара."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sku: str
    name: str
    description: str
    category: str
    brand: str
    supplier: str
    price: MoneyRead
    cost: MoneyRead
    stock: int
    is_in_stock: bool
    sales_per_month: int
    avg_rating: RatingValue
    review_count: int
    margin: MarginRead
    source_updated_at: date | None
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class Page[T](BaseModel):
    """Страница результатов (offset-пагинация)."""

    items: list[T]
    total: int
    limit: int
    offset: int


class ReferenceRead(BaseModel):
    """Элемент справочника."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    product_count: int


class CategoryMarginRead(BaseModel):
    """Агрегат маржинальности по категории."""

    model_config = ConfigDict(from_attributes=True)
    category: str
    product_count: int
    avg_margin_percent: PercentOpt
    min_margin_percent: PercentOpt
    max_margin_percent: PercentOpt
