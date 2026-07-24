"""DTO чтения из catalog-service (авторитетные товары)."""

from dataclasses import dataclass
from decimal import Decimal

from research_agent_service.domain.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    """Авторитетный товар из catalog (цена/остаток/маржа — источник истины)."""

    sku: str
    name: str
    category: str
    brand: str
    supplier: str
    price: Money
    cost: Money
    stock: int
    is_in_stock: bool
    margin_percent: Decimal | None = None
    sales_per_month: int | None = None
    avg_rating: Decimal | None = None
    review_count: int | None = None


@dataclass(frozen=True, slots=True)
class CatalogFetch:
    """Ответ batch-чтения по списку sku: найденные товары и отсутствующие."""

    products: tuple[CatalogProduct, ...]
    missing_skus: tuple[str, ...] = ()
