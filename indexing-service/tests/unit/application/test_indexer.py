"""Тесты разделяемых операций индексации (index_snapshot, tombstone)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.indexer import index_snapshot, tombstone
from indexing_service.domain.value_objects.identifiers import ProductId
from tests.support.fakes import (
    FakeEmbeddingModel,
    FakeVectorIndex,
    FixedClock,
)

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
PID = ProductId(UUID(int=1))


def _snapshot(version: int = 1) -> ProductSnapshot:
    return ProductSnapshot(
        product_id=UUID(int=1),
        sku="PROD-001",
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
        aggregate_version=version,
    )


async def test_index_snapshot_upserts_full_point():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    await index_snapshot(
        _snapshot(3), index=index, embedder=embedder, clock=FixedClock(NOW)
    )
    assert embedder.calls == 1
    assert len(index.upserts) == 1
    payload = index.payload_of(PID)
    assert payload["price"] == 129.99
    assert payload["aggregate_version"] == 3
    assert payload["is_deleted"] is False


async def test_tombstone_marks_deleted_and_keeps_version():
    index = FakeVectorIndex()
    index.preload(
        PID,
        {
            "aggregate_version": 5,
            "model_version": "m",
            "indexed_at": NOW.isoformat(),
            "content_hash": None,
        },
    )
    await tombstone(PID, index=index, clock=FixedClock(NOW), version=8)
    payload = index.payload_of(PID)
    assert payload["is_deleted"] is True
    assert payload["aggregate_version"] == 8
