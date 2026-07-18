"""Integration-тесты персистентности на реальном Postgres."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from catalog_service.application.dto.commands import (
    CreateProductCommand,
    DeleteProductCommand,
)
from catalog_service.application.dto.seed import RawProductRow
from catalog_service.application.exceptions import (
    ConcurrencyConflict,
    DuplicateSku,
)
from catalog_service.application.use_cases.create_product import CreateProduct
from catalog_service.application.use_cases.delete_product import DeleteProduct
from catalog_service.application.use_cases.seed_catalog import SeedCatalog
from catalog_service.domain.value_objects.references import (
    BrandRef,
    CategoryRef,
    SupplierRef,
)
from catalog_service.domain.value_objects.sku import Sku
from catalog_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from catalog_service.infrastructure.services.clock import SystemClock
from catalog_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)
from tests.support.factories import make_product

pytestmark = pytest.mark.integration


class _Source:
    def __init__(self, rows: list[RawProductRow]) -> None:
        self._rows = rows

    def __iter__(self) -> Iterator[RawProductRow]:
        return iter(self._rows)


def _create_uc(sm: async_sessionmaker) -> CreateProduct:
    return CreateProduct(
        uow=SqlAlchemyUnitOfWork(sm),
        clock=SystemClock(),
        id_gen=Uuid7Generator(),
        default_currency="RUB",
    )


def _cmd(**over) -> CreateProductCommand:
    base = {
        "sku": "PROD-1",
        "name": "Наушники",
        "description": "Опис",
        "category_name": "Электроника",
        "brand_name": "AudioMax",
        "supplier_name": "TechSupply Co",
        "price_amount": Decimal("129.99"),
        "cost_amount": Decimal("65.00"),
        "stock_quantity": 245,
        "sales_per_month": 87,
        "avg_rating": Decimal("4.5"),
        "review_count": 1243,
    }
    base.update(over)
    return CreateProductCommand(**base)


def _raw(sku: str, **over) -> RawProductRow:
    base = {
        "name": "Наушники",
        "description": "Опис",
        "category_name": "Электроника",
        "brand_name": "AudioMax",
        "price": "129.99",
        "cost": "65.00",
        "stock": "245",
        "sales_per_month": "87",
        "avg_rating": "4.5",
        "review_count": "1243",
        "supplier_name": "TechSupply Co",
        "source_updated_at": "2024-03-15",
    }
    base.update(over)
    return RawProductRow(line_no=2, sku=sku, **base)


async def _count(sm: async_sessionmaker, table: str) -> int:
    async with sm() as session:
        return (
            await session.execute(text(f"SELECT count(*) FROM {table}"))
        ).scalar_one()


async def test_create_persists_product_and_outbox(sm):
    result = await _create_uc(sm).execute(_cmd())
    assert result.version == 1
    assert await _count(sm, "products") == 1
    assert await _count(sm, "outbox") == 1


async def test_get_by_sku_roundtrip(sm):
    await _create_uc(sm).execute(_cmd(sku="PROD-9"))
    async with SqlAlchemyUnitOfWork(sm) as uow:
        restored = await uow.products.get_by_sku(Sku("PROD-9"))
    assert restored is not None
    assert restored.pricing.price.amount == Decimal("129.99")
    assert restored.category.name == "Электроника"
    assert restored.metrics.avg_rating.value == Decimal("4.50")


async def test_reference_get_or_create_is_idempotent(sm):
    async with SqlAlchemyUnitOfWork(sm) as uow:
        first = await uow.categories.get_or_create("Электроника")
        second = await uow.categories.get_or_create("Электроника")
        await uow.commit()
    assert first.id == second.id
    assert await _count(sm, "categories") == 1


async def test_optimistic_lock_conflict(sm):
    await _create_uc(sm).execute(_cmd(sku="PROD-1"))
    async with SqlAlchemyUnitOfWork(sm) as uow1:
        stale = await uow1.products.get_by_sku(Sku("PROD-1"))
        async with SqlAlchemyUnitOfWork(sm) as uow2:
            fresh = await uow2.products.get_by_sku(Sku("PROD-1"))
            fresh.change_content(name="Победитель", now=SystemClock().now())
            await uow2.products.update(fresh, expected_version=1)
            await uow2.commit()
        stale.change_content(name="Проигравший", now=SystemClock().now())
        with pytest.raises(ConcurrencyConflict):
            await uow1.products.update(stale, expected_version=1)


async def test_sku_reserved_after_soft_delete(sm):
    result = await _create_uc(sm).execute(_cmd(sku="PROD-1"))
    await DeleteProduct(
        uow=SqlAlchemyUnitOfWork(sm),
        clock=SystemClock(),
        id_gen=Uuid7Generator(),
    ).execute(
        DeleteProductCommand(product_id=result.product_id, expected_version=1)
    )
    with pytest.raises(DuplicateSku):
        await _create_uc(sm).execute(_cmd(sku="PROD-1"))


async def test_margin_generated_column(sm):
    await _create_uc(sm).execute(
        _cmd(
            sku="PROD-1",
            price_amount=Decimal("100.00"),
            cost_amount=Decimal("25.00"),
        )
    )
    async with sm() as session:
        margin = (
            await session.execute(
                text("SELECT margin_percent FROM products WHERE sku = 'PROD-1'")
            )
        ).scalar_one()
    assert margin == Decimal("75.00")


async def test_seed_is_idempotent_on_real_db(sm):
    rows = [_raw("PROD-1"), _raw("PROD-2")]

    def _seed() -> SeedCatalog:
        return SeedCatalog(
            uow=SqlAlchemyUnitOfWork(sm),
            source=_Source(rows),
            clock=SystemClock(),
            id_gen=Uuid7Generator(),
            default_currency="RUB",
        )

    first = await _seed().execute()
    assert first.created == 2
    assert await _count(sm, "outbox") == 2

    second = await _seed().execute()
    assert second.created == 0
    assert second.events_emitted == 0
    assert await _count(sm, "outbox") == 2


async def test_repository_add_existing_sku_raises_duplicate(sm):
    await _create_uc(sm).execute(_cmd(sku="PROD-1"))
    async with SqlAlchemyUnitOfWork(sm) as uow:
        category = await uow.categories.get_or_create("Электроника")
        brand = await uow.brands.get_or_create("AudioMax")
        supplier = await uow.suppliers.get_or_create("TechSupply Co")
        duplicate = make_product(
            sku="PROD-1",
            category=CategoryRef(category.id, category.name),
            brand=BrandRef(brand.id, brand.name),
            supplier=SupplierRef(supplier.id, supplier.name),
        )
        with pytest.raises(DuplicateSku):
            await uow.products.add(duplicate)
