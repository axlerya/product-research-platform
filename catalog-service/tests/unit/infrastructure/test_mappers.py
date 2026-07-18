"""Тесты ручного маппера ORM <-> домен (без БД)."""

from datetime import UTC, datetime
from decimal import Decimal

from catalog_service.infrastructure.db.base import Base
from catalog_service.infrastructure.db.mappers import ProductMapper
from catalog_service.infrastructure.db.models import (
    BrandORM,
    CategoryORM,
    ProductORM,
    SupplierORM,
)
from tests.support.factories import make_pricing, make_product

_NOW = datetime(2026, 7, 18, tzinfo=UTC)


def _hydrate(row: ProductORM, product) -> ProductORM:
    """Проставляет relationship-справочники (в БД это делает JOIN)."""
    row.category = CategoryORM(
        id=product.category.id.value,
        name=product.category.name,
        created_at=_NOW,
    )
    row.brand = BrandORM(
        id=product.brand.id.value, name=product.brand.name, created_at=_NOW
    )
    row.supplier = SupplierORM(
        id=product.supplier.id.value,
        name=product.supplier.name,
        created_at=_NOW,
    )
    return row


def test_metadata_registers_expected_tables():
    tables = set(Base.metadata.tables)
    assert {
        "products",
        "categories",
        "brands",
        "suppliers",
        "outbox",
    } <= tables


def test_roundtrip_preserves_fields():
    product = make_product(sku="PROD-001")
    row = _hydrate(ProductMapper.to_orm(product), product)
    restored = ProductMapper.to_domain(row)
    assert restored.sku == product.sku
    assert restored.name == product.name
    assert restored.pricing.price.amount == product.pricing.price.amount
    assert restored.pricing.cost.amount == product.pricing.cost.amount
    assert restored.category.name == product.category.name
    assert restored.brand.name == product.brand.name
    assert restored.supplier.name == product.supplier.name
    assert restored.stock.quantity == product.stock.quantity
    assert restored.metrics.avg_rating.value == product.metrics.avg_rating.value
    assert restored.version == product.version


def test_to_orm_keeps_decimal_and_currency():
    product = make_product(pricing=make_pricing("129.99", "65.00"))
    row = ProductMapper.to_orm(product)
    assert row.price_amount == Decimal("129.99")
    assert isinstance(row.price_amount, Decimal)
    assert row.currency == "RUB"


def test_to_domain_does_not_emit_events():
    product = make_product()
    restored = ProductMapper.to_domain(
        _hydrate(ProductMapper.to_orm(product), product)
    )
    assert restored.collect_events() == []
