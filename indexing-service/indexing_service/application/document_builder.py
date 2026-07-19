"""Сборка доменной сущности ``ProductDocument`` из снимка catalog.

Граница «сырые данные → чистый домен»: строит доменные VO из примитивов
снимка. Доменные исключения ловит вызывающий use case и переводит в
``PermanentError`` (poison).
"""

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.domain.entities.product_document import ProductDocument
from indexing_service.domain.value_objects.currency import Currency
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.metrics import ProductMetrics
from indexing_service.domain.value_objects.money import Money
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.rating import Rating
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.domain.value_objects.stock import StockLevel


def to_product_document(snapshot: ProductSnapshot) -> ProductDocument:
    """Строит ``ProductDocument`` из снимка (валидация — в домене).

    Args:
        snapshot: Снимок товара из catalog.

    Returns:
        Готовая к индексации сущность.

    Raises:
        DomainError: Если значения снимка нарушают доменные инварианты.
    """
    currency = Currency(snapshot.currency)
    pricing = Pricing(
        price=Money.of(snapshot.price, currency),
        cost=Money.of(snapshot.cost, currency),
    )
    metrics = ProductMetrics(
        sales_per_month=snapshot.sales_per_month,
        avg_rating=Rating(snapshot.avg_rating),
        review_count=snapshot.review_count,
    )
    return ProductDocument(
        product_id=ProductId(snapshot.product_id),
        sku=Sku(snapshot.sku),
        name=snapshot.name,
        description=snapshot.description,
        category=snapshot.category,
        brand=snapshot.brand,
        supplier=snapshot.supplier,
        pricing=pricing,
        stock=StockLevel(snapshot.stock),
        metrics=metrics,
        source_updated_at=snapshot.source_updated_at,
        aggregate_version=snapshot.aggregate_version,
    )
