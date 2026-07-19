"""Тесты ``ReindexCatalog`` (§8) на фейках."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.use_cases.reindex_catalog import (
    ReindexCatalog,
)
from tests.support.fakes import (
    FakeCatalogGateway,
    FakeEmbeddingModel,
    FakeVectorIndexAdmin,
    FixedClock,
)

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)


def _snapshot(seq: int) -> ProductSnapshot:
    return ProductSnapshot(
        product_id=UUID(int=seq),
        sku=f"PROD-{seq:03d}",
        name="Наушники",
        description="Беспроводные",
        category="Электроника",
        brand="AudioMax",
        supplier="TechSupply",
        price=Decimal("129.99"),
        cost=Decimal("65.00"),
        currency="RUB",
        stock=245,
        sales_per_month=87,
        avg_rating=Decimal("4.5"),
        review_count=1243,
        source_updated_at=date(2024, 3, 15),
        aggregate_version=1,
    )


async def test_reindex_provisions_backfills_and_swaps():
    admin = FakeVectorIndexAdmin()
    catalog = FakeCatalogGateway([_snapshot(1), _snapshot(2)])
    reindex = ReindexCatalog(
        admin=admin,
        embedder=FakeEmbeddingModel(),
        catalog=catalog,
        clock=FixedClock(NOW),
    )
    report = await reindex.execute(
        target_collection="products_v2", alias="products"
    )
    assert report.indexed == 2
    assert report.errors == 0
    assert admin.provisioned == ["products_v2"]
    assert admin.swaps == [("products", "products_v2")]
    assert len(admin.index.upserts) == 2
