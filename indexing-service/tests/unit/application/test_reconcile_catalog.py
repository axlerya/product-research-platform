"""Тесты ``ReconcileCatalog`` (§9) на фейках."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.use_cases.reconcile_catalog import (
    ReconcileCatalog,
)
from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from tests.support.fakes import (
    FakeCatalogGateway,
    FakeEmbeddingModel,
    FakeVectorIndex,
    FixedClock,
)

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
MODEL_KEY = "fake@v1|pool=cls|norm=1|dim=4"


def _snapshot(seq: int, version: int, name: str = "Наушники"):
    return ProductSnapshot(
        product_id=UUID(int=seq),
        sku="PROD-001",
        name=name,
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
        aggregate_version=version,
    )


def _hash(name: str = "Наушники") -> str:
    text = compose(
        name=name,
        brand="AudioMax",
        category="Электроника",
        description="Беспроводные",
    )
    return ContentHash.of(text.value).value


def _wm(version: int, content_hash: str | None) -> dict:
    return {
        "aggregate_version": version,
        "model_version": MODEL_KEY,
        "content_hash": content_hash,
        "indexed_at": NOW.isoformat(),
    }


def _reconcile(index, embedder, catalog) -> ReconcileCatalog:
    return ReconcileCatalog(
        index=index,
        embedder=embedder,
        catalog=catalog,
        clock=FixedClock(NOW),
    )


async def test_missing_is_indexed():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    catalog = FakeCatalogGateway([_snapshot(1, 1)])
    report = await _reconcile(index, embedder, catalog).execute()
    assert report.indexed == 1
    assert index.exists(ProductId(UUID(int=1)))


async def test_up_to_date_matched():
    index = FakeVectorIndex()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash()))
    report = await _reconcile(
        index, FakeEmbeddingModel(), FakeCatalogGateway([_snapshot(1, 5)])
    ).execute()
    assert report.matched == 1


async def test_metrics_drift_repaired_without_reembed():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash()))
    catalog = FakeCatalogGateway([_snapshot(1, 6)])  # версия бумпнута
    report = await _reconcile(index, embedder, catalog).execute()
    assert report.repaired == 1
    assert embedder.calls == 0
    assert index.payload_of(ProductId(UUID(int=1)))["aggregate_version"] == 6


async def test_text_drift_reembeds():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash("Наушники")))
    catalog = FakeCatalogGateway([_snapshot(1, 6, name="Новое имя")])
    report = await _reconcile(index, embedder, catalog).execute()
    assert report.repaired == 1
    assert embedder.calls == 1


async def test_orphan_tombstoned():
    index = FakeVectorIndex()
    index.preload(ProductId(UUID(int=9)), _wm(3, None))
    report = await _reconcile(
        index, FakeEmbeddingModel(), FakeCatalogGateway([])
    ).execute()
    assert report.tombstoned == 1
    assert index.payload_of(ProductId(UUID(int=9)))["is_deleted"] is True
