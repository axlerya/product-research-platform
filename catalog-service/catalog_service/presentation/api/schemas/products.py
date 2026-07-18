"""Схемы запросов для товаров (мульти-модельный паттерн)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from catalog_service.presentation.api.schemas.common import (
    Amount,
    RatingValue,
    SkuField,
)


class ProductCreate(BaseModel):
    """POST /products. Валюта не передаётся (единая валюта сервиса)."""

    model_config = ConfigDict(extra="forbid")

    sku: SkuField
    name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20_000)
    category: str = Field(min_length=1, max_length=200)
    brand: str = Field(min_length=1, max_length=200)
    supplier: str = Field(min_length=1, max_length=200)
    price: Amount
    cost: Amount
    stock: int = Field(ge=0)
    sales_per_month: int = Field(default=0, ge=0)
    avg_rating: RatingValue = Decimal("0.00")
    review_count: int = Field(default=0, ge=0)
    source_updated_at: date | None = None


class ProductContentUpdate(BaseModel):
    """PATCH /products/{id} — контентные поля (все опциональны)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    category: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, min_length=1, max_length=200)


class ProductCommercialUpdate(BaseModel):
    """PATCH /products/{id}/commercial — цена/себестоимость/поставщик."""

    model_config = ConfigDict(extra="forbid")

    price: Amount | None = None
    cost: Amount | None = None
    supplier: str | None = Field(default=None, min_length=1, max_length=200)


class StockUpdate(BaseModel):
    """PATCH /products/{id}/stock — абсолютная установка остатка."""

    model_config = ConfigDict(extra="forbid")

    stock: int = Field(ge=0)


class MetricsUpdate(BaseModel):
    """PATCH /products/{id}/metrics — полная замена метрик."""

    model_config = ConfigDict(extra="forbid")

    sales_per_month: int = Field(ge=0)
    avg_rating: RatingValue
    review_count: int = Field(ge=0)
