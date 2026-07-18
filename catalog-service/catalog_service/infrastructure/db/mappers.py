"""Ручной Data Mapper: ORM-модель <-> доменный агрегат.

Домену запрещён импорт SQLAlchemy, поэтому маппинг живёт в инфраструктуре.
Реконструкция агрегата — через ``Product.reconstitute`` (без эмиссии
``ProductCreated``). Справочные имена гидрируются из загруженных
relationship (``row.category`` и т.п.).
"""

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
from catalog_service.infrastructure.db.models import ProductORM


class ProductMapper:
    """Преобразование между ``ProductORM`` и доменным ``Product``."""

    @staticmethod
    def to_domain(row: ProductORM) -> Product:
        """Восстанавливает доменный агрегат из строки БД.

        Args:
            row: ORM-строка с загруженными ``category``/``brand``/
                ``supplier`` (иначе relationship бросит из-за
                ``lazy="raise"``).

        Returns:
            Реконструированный ``Product`` (без доменного события).
        """
        currency = Currency(row.currency)
        pricing = Pricing(
            price=Money(row.price_amount, currency),
            cost=Money(row.cost_amount, currency),
        )
        metrics = ProductMetrics(
            sales_per_month=row.sales_per_month,
            avg_rating=Rating(row.avg_rating),
            review_count=row.review_count,
        )
        return Product.reconstitute(
            id=ProductId(row.id),
            sku=Sku(row.sku),
            name=row.name,
            description=row.description,
            category=CategoryRef(
                CategoryId(row.category_id), row.category.name
            ),
            brand=BrandRef(BrandId(row.brand_id), row.brand.name),
            supplier=SupplierRef(
                SupplierId(row.supplier_id), row.supplier.name
            ),
            pricing=pricing,
            stock=StockLevel(row.stock_quantity),
            metrics=metrics,
            source_updated_at=row.source_updated_at,
            version=row.version,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )

    @staticmethod
    def to_orm(product: Product) -> ProductORM:
        """Строит ORM-строку из доменного агрегата (для INSERT).

        ``margin_percent`` не задаётся (GENERATED-колонка).
        """
        return ProductORM(
            id=product.id.value,
            sku=product.sku.value,
            name=product.name,
            description=product.description,
            category_id=product.category.id.value,
            brand_id=product.brand.id.value,
            supplier_id=product.supplier.id.value,
            price_amount=product.pricing.price.amount,
            cost_amount=product.pricing.cost.amount,
            currency=product.pricing.price.currency.code,
            stock_quantity=product.stock.quantity,
            sales_per_month=product.metrics.sales_per_month,
            avg_rating=product.metrics.avg_rating.value,
            review_count=product.metrics.review_count,
            source_updated_at=product.source_updated_at,
            version=product.version,
            is_deleted=product.is_deleted,
            created_at=product.created_at,
            updated_at=product.updated_at,
            deleted_at=product.deleted_at,
        )
