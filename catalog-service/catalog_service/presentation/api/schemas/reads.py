"""Схемы чтения (из application-DTO ``*View``) и запрос batch-чтения."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from catalog_service.presentation.api.schemas.common import (
    Amount,
    PercentOpt,
    RatingValue,
)

# Артикул в batch-запросе не валидируется паттерном: неизвестный артикул —
# это ``missing_skus`` в ответе, а не 422 на весь запрос.
SkuItem = Annotated[str, Field(min_length=1, max_length=64)]
MAX_BATCH_SKUS = 500


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


class ProductsBySkusRequest(BaseModel):
    """POST /products/by-skus — batch-чтение по списку артикулов."""

    model_config = ConfigDict(extra="forbid")

    skus: list[SkuItem] = Field(default_factory=list, max_length=MAX_BATCH_SKUS)
    include_deleted: bool = False


class ProductBatchRead(BaseModel):
    """Ответ batch-чтения по артикулам: найденные и отсутствующие."""

    model_config = ConfigDict(from_attributes=True)
    products: list[ProductRead]
    missing_skus: list[str]


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
