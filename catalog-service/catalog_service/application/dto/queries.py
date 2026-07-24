"""DTO запросов чтения (фильтры, пагинация, сортировка)."""

from dataclasses import dataclass
from decimal import Decimal

# Разрешённые поля сортировки: токен -> колонка (направление задаёт префикс
# ``-``). Инфраструктура собирает из этого безопасный ORDER BY (whitelist).
SORT_COLUMNS: dict[str, str] = {
    "created_at": "created_at",
    "price": "price_amount",
    "margin": "margin_percent",
    "rating": "avg_rating",
    "sales": "sales_per_month",
    "name": "name",
}


@dataclass(frozen=True, slots=True)
class MarginBandSpec:
    """Границы одного бэнда маржи в процентах (полуинтервал).

    Attributes:
        label: Метка бэнда в ответе.
        lower_percent: Нижняя граница включительно (``None`` — без границы).
        upper_percent: Верхняя граница исключительно (``None`` — без границы).
    """

    label: str
    lower_percent: Decimal | None = None
    upper_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PriceAnalysisSelector:
    """Отбор товаров для ценового анализа: явные артикулы ИЛИ фасеты.

    Непустой ``skus`` сужает срез до перечисленных артикулов; остальные
    поля работают как фильтры поиска и комбинируются с ним по «И».
    """

    skus: tuple[str, ...] = ()
    text: str | None = None
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


@dataclass(frozen=True, slots=True)
class ProductSearchQuery:
    """Критерии поиска/фильтрации товаров."""

    text: str | None = None
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
    sort: str = "-created_at"
    limit: int = 20
    offset: int = 0
