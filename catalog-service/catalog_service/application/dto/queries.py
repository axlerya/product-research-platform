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
