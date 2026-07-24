"""Типизированные контракты аргументов инструментов (structured tool-calling).

LLM заполняет эти pydantic-модели; они валидируют вход и переводятся в DTO
прикладного слоя. Недоверенный JSON от модели не доходит до сервисов сырым —
только через провалидированные и суженные до безопасных фасетов структуры.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from research_agent_service.application.dto.price_analysis import (
    MarginBandSpec,
    ProductSelector,
)
from research_agent_service.domain.value_objects.query import QueryFilters


class ProductCatalogRagArgs(BaseModel):
    """Аргументы product_catalog_rag: запрос и безопасные фасеты."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Поисковый запрос по каталогу товаров")
    category: str | None = Field(default=None, description="Категория")
    brand: str | None = Field(default=None, description="Бренд")
    in_stock: bool | None = Field(
        default=None, description="Только товары в наличии"
    )
    price_min: Decimal | None = Field(default=None, description="Цена от")
    price_max: Decimal | None = Field(default=None, description="Цена до")

    def to_filters(self) -> QueryFilters | None:
        """Строит QueryFilters или None, если фасеты не заданы."""
        if not self._has_facets():
            return None
        return QueryFilters(
            category=self.category,
            brand=self.brand,
            in_stock=self.in_stock,
            price_min=self.price_min,
            price_max=self.price_max,
        )

    def _has_facets(self) -> bool:
        return any(
            value is not None
            for value in (
                self.category,
                self.brand,
                self.in_stock,
                self.price_min,
                self.price_max,
            )
        )


class MarginBandArg(BaseModel):
    """Границы одного бэнда маржи (проценты)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Метка бэнда")
    lower_percent: Decimal | None = Field(
        default=None, description="Нижняя граница, %"
    )
    upper_percent: Decimal | None = Field(
        default=None, description="Верхняя граница, %"
    )

    def to_spec(self) -> MarginBandSpec:
        """Переводит в MarginBandSpec прикладного слоя."""
        return MarginBandSpec(
            label=self.label,
            lower_percent=self.lower_percent,
            upper_percent=self.upper_percent,
        )


class PriceAnalysisArgs(BaseModel):
    """Аргументы price_analysis: селектор товаров и бэнды маржи."""

    model_config = ConfigDict(extra="forbid")

    skus: list[str] = Field(
        default_factory=list, description="Явный список SKU"
    )
    category: str | None = Field(default=None, description="Категория")
    brand: str | None = Field(default=None, description="Бренд")
    supplier: str | None = Field(default=None, description="Поставщик")
    text: str | None = Field(default=None, description="Текстовый отбор")
    in_stock: bool | None = Field(default=None, description="Только в наличии")
    price_min: Decimal | None = Field(default=None, description="Цена от")
    price_max: Decimal | None = Field(default=None, description="Цена до")
    bands: list[MarginBandArg] = Field(
        default_factory=list, description="Бэнды маржи для распределения"
    )

    def to_selector(self) -> ProductSelector:
        """Переводит в ProductSelector прикладного слоя."""
        return ProductSelector(
            skus=tuple(self.skus),
            category=self.category,
            brand=self.brand,
            supplier=self.supplier,
            text=self.text,
            in_stock=self.in_stock,
            price_min=self.price_min,
            price_max=self.price_max,
        )

    def to_bands(self) -> tuple[MarginBandSpec, ...]:
        """Переводит бэнды в кортеж MarginBandSpec."""
        return tuple(band.to_spec() for band in self.bands)


class WebSearchArgs(BaseModel):
    """Аргументы web_search: запрос и число результатов."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Поисковый запрос во внешнем вебе")
    k: int = Field(default=5, ge=1, le=10, description="Сколько результатов")
