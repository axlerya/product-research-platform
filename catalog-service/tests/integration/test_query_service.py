"""Integration-тесты read-сервисов на реальном Postgres."""

from decimal import Decimal

import pytest

from catalog_service.application.dto.commands import CreateProductCommand
from catalog_service.application.dto.queries import ProductSearchQuery
from catalog_service.application.use_cases.create_product import CreateProduct
from catalog_service.infrastructure.db.repositories.query_service import (
    SqlAlchemyProductQueryService,
    SqlAlchemyReferenceQueryService,
)
from catalog_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from catalog_service.infrastructure.services.clock import SystemClock
from catalog_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)

pytestmark = pytest.mark.integration


async def _create(sm, **over):
    base = {
        "sku": "PROD-1",
        "name": "Наушники",
        "description": "Опис",
        "category_name": "Электроника",
        "brand_name": "AudioMax",
        "supplier_name": "TechSupply Co",
        "price_amount": Decimal("100.00"),
        "cost_amount": Decimal("25.00"),
        "stock_quantity": 10,
        "sales_per_month": 50,
        "avg_rating": Decimal("4.5"),
        "review_count": 100,
    }
    base.update(over)
    return await CreateProduct(
        uow=SqlAlchemyUnitOfWork(sm),
        clock=SystemClock(),
        id_gen=Uuid7Generator(),
        default_currency="RUB",
    ).execute(CreateProductCommand(**base))


async def test_get_by_sku_returns_view(sm):
    await _create(sm, sku="PROD-1")
    view = await SqlAlchemyProductQueryService(sm).get(sku="prod-1")
    assert view is not None
    assert view.category == "Электроника"
    assert view.is_in_stock is True
    assert view.margin.percent == Decimal("75.00")
    assert view.margin.profit.amount == Decimal("75.00")
    assert view.price.currency == "RUB"


async def test_get_by_id_returns_view(sm):
    result = await _create(sm, sku="PROD-1")
    view = await SqlAlchemyProductQueryService(sm).get(
        product_id=result.product_id
    )
    assert view is not None
    assert view.sku == "PROD-1"


async def test_get_unknown_returns_none(sm):
    assert await SqlAlchemyProductQueryService(sm).get(sku="NOPE-1") is None


async def test_get_respects_include_deleted(sm):
    from catalog_service.application.dto.commands import DeleteProductCommand
    from catalog_service.application.use_cases.delete_product import (
        DeleteProduct,
    )

    result = await _create(sm, sku="PROD-1")
    await DeleteProduct(
        uow=SqlAlchemyUnitOfWork(sm),
        clock=SystemClock(),
        id_gen=Uuid7Generator(),
    ).execute(
        DeleteProductCommand(product_id=result.product_id, expected_version=1)
    )
    qs = SqlAlchemyProductQueryService(sm)
    assert await qs.get(sku="PROD-1") is None
    assert await qs.get(sku="PROD-1", include_deleted=True) is not None


async def test_search_all_filters(sm):
    await _create(
        sm,
        sku="PROD-1",
        name="Наушники Pro",
        category_name="Электроника",
        brand_name="AudioMax",
        supplier_name="TechSupply Co",
        price_amount=Decimal("100.00"),
        cost_amount=Decimal("25.00"),
        stock_quantity=10,
        avg_rating=Decimal("4.5"),
    )
    page = await SqlAlchemyProductQueryService(sm).search(
        ProductSearchQuery(
            text="науш",
            category="Электроника",
            brand="AudioMax",
            supplier="TechSupply Co",
            price_min=Decimal("50"),
            price_max=Decimal("200"),
            in_stock=True,
            min_rating=Decimal("4.0"),
            margin_min=Decimal("50"),
            margin_max=Decimal("90"),
            include_deleted=True,
            sort="-price",
        )
    )
    assert page.total == 1
    assert page.items[0].sku == "PROD-1"


async def test_search_pagination(sm):
    for i in range(5):
        await _create(sm, sku=f"PROD-{i}")
    page = await SqlAlchemyProductQueryService(sm).search(
        ProductSearchQuery(limit=2, offset=0)
    )
    assert page.total == 5
    assert len(page.items) == 2


async def test_search_margin_below_threshold(sm):
    await _create(
        sm, sku="PROD-1", price_amount=Decimal("100"), cost_amount=Decimal("25")
    )
    await _create(
        sm, sku="PROD-2", price_amount=Decimal("100"), cost_amount=Decimal("80")
    )
    page = await SqlAlchemyProductQueryService(sm).search(
        ProductSearchQuery(margin_max=Decimal("40"))
    )
    assert page.total == 1
    assert page.items[0].sku == "PROD-2"


async def test_search_out_of_stock(sm):
    await _create(sm, sku="PROD-1", stock_quantity=0)
    await _create(sm, sku="PROD-2", stock_quantity=5)
    qs = SqlAlchemyProductQueryService(sm)
    assert (await qs.search(ProductSearchQuery(in_stock=False))).total == 1


async def test_margin_by_category(sm):
    # Маржи 75.00, 25.00, 60.00 -> avg 53.3333... должно округлиться до 53.33.
    for sku, cost in (("PROD-1", "25"), ("PROD-2", "75"), ("PROD-3", "40")):
        await _create(
            sm,
            sku=sku,
            category_name="Электроника",
            price_amount=Decimal("100"),
            cost_amount=Decimal(cost),
        )
    rows = await SqlAlchemyProductQueryService(sm).margin_by_category(
        include_deleted=True
    )
    assert len(rows) == 1
    assert rows[0].category == "Электроника"
    assert rows[0].product_count == 3
    assert rows[0].avg_margin_percent == Decimal("53.33")
    assert rows[0].min_margin_percent == Decimal("25.00")
    assert rows[0].max_margin_percent == Decimal("75.00")


async def test_list_references_with_counts(sm):
    await _create(sm, sku="PROD-1", category_name="Электроника")
    await _create(sm, sku="PROD-2", category_name="Электроника")
    qs = SqlAlchemyReferenceQueryService(sm)
    categories = await qs.list_categories()
    assert len(categories) == 1
    assert categories[0].name == "Электроника"
    assert categories[0].product_count == 2
    assert (await qs.list_brands())[0].product_count == 2
    assert (await qs.list_suppliers())[0].product_count == 2
