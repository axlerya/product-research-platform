"""Детерминированные доменные билдеры для unit-тестов.

Собирают валидные доменные объекты с разумными дефолтами и
точечным переопределением. Все временные метки и идентификаторы —
фиксированные (детерминизм golden-снимков событий).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from catalog_service.domain.entities.product import Product
from catalog_service.domain.value_objects.currency import Currency
from catalog_service.domain.value_objects.identifiers import (
    BrandId,
    CategoryId,
    ProductId,
    SupplierId,
)
from catalog_service.domain.value_objects.metrics import ProductMetrics
from catalog_service.domain.value_objects.money import Money
from catalog_service.domain.value_objects.pricing import Pricing
from catalog_service.domain.value_objects.rating import Rating
from catalog_service.domain.value_objects.references import (
    BrandRef,
    CategoryRef,
    SupplierRef,
)
from catalog_service.domain.value_objects.sku import Sku
from catalog_service.domain.value_objects.stock import StockLevel

RUB = Currency("RUB")
FIXED_NOW = datetime(2026, 7, 18, 10, 15, 30, tzinfo=UTC)
PRODUCT_ID = ProductId(UUID("0192f0c8-7b3a-7e2d-9a1c-000000000001"))


def make_pricing(
    price: str = "129.99",
    cost: str = "65.00",
    currency: Currency = RUB,
) -> Pricing:
    """Строит ``Pricing`` из строковых сумм (без float)."""
    return Pricing(
        price=Money.of(Decimal(price), currency),
        cost=Money.of(Decimal(cost), currency),
    )


def make_metrics(
    sales: int = 87,
    rating: str = "4.50",
    reviews: int = 1243,
) -> ProductMetrics:
    """Строит ``ProductMetrics`` с рейтингом-строкой."""
    return ProductMetrics(
        sales_per_month=sales,
        avg_rating=Rating(Decimal(rating)),
        review_count=reviews,
    )


def make_category_ref(name: str = "Электроника") -> CategoryRef:
    """Строит снимок-ссылку на категорию."""
    return CategoryRef(id=CategoryId(UUID(int=1)), name=name)


def make_brand_ref(name: str = "AudioMax") -> BrandRef:
    """Строит снимок-ссылку на бренд."""
    return BrandRef(id=BrandId(UUID(int=2)), name=name)


def make_supplier_ref(name: str = "TechSupply Co") -> SupplierRef:
    """Строит снимок-ссылку на поставщика."""
    return SupplierRef(id=SupplierId(UUID(int=3)), name=name)


def make_product(
    *,
    sku: str = "PROD-001",
    name: str = "Наушники",
    description: str = "Описание",
    version: int = 1,
    is_deleted: bool = False,
    pricing: Pricing | None = None,
    stock: int = 245,
    metrics: ProductMetrics | None = None,
    category: CategoryRef | None = None,
    brand: BrandRef | None = None,
    supplier: SupplierRef | None = None,
) -> Product:
    """Восстанавливает валидный ``Product`` (без события создания).

    Используется как отправная точка для тестов мутаций агрегата.
    """
    return Product.reconstitute(
        id=PRODUCT_ID,
        sku=Sku(sku),
        name=name,
        description=description,
        category=category or make_category_ref(),
        brand=brand or make_brand_ref(),
        supplier=supplier or make_supplier_ref(),
        pricing=pricing or make_pricing(),
        stock=StockLevel(stock),
        metrics=metrics or make_metrics(),
        source_updated_at=date(2024, 3, 15),
        version=version,
        is_deleted=is_deleted,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
        deleted_at=None,
    )
