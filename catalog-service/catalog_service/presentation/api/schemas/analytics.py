"""Схемы ценового анализа: селектор среза (запрос) и статистика (ответ)."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from catalog_service.application.dto.queries import (
    MarginBandSpec,
    PriceAnalysisSelector,
)
from catalog_service.presentation.api.schemas.common import (
    Amount,
    StatPercent,
    StatPercentOpt,
)
from catalog_service.presentation.api.schemas.reads import MoneyRead

# Артикул в селекторе не валидируется паттерном: неизвестный артикул — это
# пустой срез, а не ошибка запроса.
SkuItem = Annotated[str, Field(min_length=1, max_length=64)]
MAX_SKUS = 500


class MarginBandRequest(BaseModel):
    """Границы одного бэнда маржи (проценты, полуинтервал)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)
    lower_percent: Decimal | None = None
    upper_percent: Decimal | None = None

    def to_spec(self) -> MarginBandSpec:
        """Переводит в ``MarginBandSpec`` прикладного слоя."""
        return MarginBandSpec(
            label=self.label,
            lower_percent=self.lower_percent,
            upper_percent=self.upper_percent,
        )


class PriceSelectorRequest(BaseModel):
    """Отбор товаров для анализа: явные артикулы и/или фасеты."""

    model_config = ConfigDict(extra="forbid")

    skus: list[SkuItem] = Field(default_factory=list, max_length=MAX_SKUS)
    text: str | None = Field(default=None, max_length=500)
    category: str | None = None
    brand: str | None = None
    supplier: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    in_stock: bool | None = None
    min_rating: Decimal | None = None
    margin_min: Decimal | None = None
    margin_max: Decimal | None = None
    include_deleted: bool = False

    def to_selector(self) -> PriceAnalysisSelector:
        """Переводит в ``PriceAnalysisSelector`` прикладного слоя."""
        return PriceAnalysisSelector(
            skus=tuple(self.skus),
            text=self.text,
            category=self.category,
            brand=self.brand,
            supplier=self.supplier,
            price_min=self.price_min,
            price_max=self.price_max,
            in_stock=self.in_stock,
            min_rating=self.min_rating,
            margin_min=self.margin_min,
            margin_max=self.margin_max,
            include_deleted=self.include_deleted,
        )


class PriceAnalysisRequest(BaseModel):
    """POST /analytics/prices — срез и бэнды маржи."""

    model_config = ConfigDict(extra="forbid")

    selector: PriceSelectorRequest = Field(default_factory=PriceSelectorRequest)
    bands: list[MarginBandRequest] = Field(default_factory=list, max_length=20)

    def to_bands(self) -> tuple[MarginBandSpec, ...]:
        """Переводит бэнды в кортеж спецификаций."""
        return tuple(band.to_spec() for band in self.bands)


class PriceStatsRead(BaseModel):
    """Статистика цен в ответе (суммы строками)."""

    model_config = ConfigDict(from_attributes=True)
    min: Amount
    max: Amount
    avg: Amount
    median: Amount
    stddev: Amount


class MarginStatsRead(BaseModel):
    """Статистика маржи в ответе (проценты строками)."""

    model_config = ConfigDict(from_attributes=True)
    min_percent: StatPercent
    max_percent: StatPercent
    avg_percent: StatPercent
    median_percent: StatPercent
    undefined_count: int
    negative_count: int


class MarginBandRead(BaseModel):
    """Бэнд маржи с числом попавших товаров."""

    model_config = ConfigDict(from_attributes=True)
    label: str
    count: int
    lower_percent: StatPercentOpt
    upper_percent: StatPercentOpt


class PriceOutlierRead(BaseModel):
    """Ценовой выброс: товар, цена, направление и скор."""

    model_config = ConfigDict(from_attributes=True)
    sku: str
    price: MoneyRead
    reason: str
    score: Amount


class PriceAnalysisRead(BaseModel):
    """Готовый ценовой анализ среза."""

    model_config = ConfigDict(from_attributes=True)
    count: int
    currency: str
    price: PriceStatsRead
    margin: MarginStatsRead
    analysis_ref: str
    bands: list[MarginBandRead]
    outliers: list[PriceOutlierRead]
