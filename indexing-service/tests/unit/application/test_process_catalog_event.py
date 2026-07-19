"""Тесты оркестратора ``ProcessCatalogEvent`` на in-memory фейках (§6).

Проверяют все ветки действий, merge-семантику сиблингов одной версии,
gap-repair, дедуп ре-эмбеддинга, защиту от воскрешения и poison.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from indexing_service.application.dto.events import (
    CommercialChangedEvent,
    ContentChangedEvent,
    ProductCreatedEvent,
    ProductDeletedEvent,
)
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.exceptions import (
    EventValidationError,
    ProductNotInCatalog,
)
from indexing_service.application.use_cases.process_catalog_event import (
    ProcessCatalogEvent,
)
from indexing_service.domain.services.change_classifier import IndexingAction
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
_UUID = UUID("0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a")
PID = ProductId(_UUID)


def _snapshot(version: int = 1, **over) -> ProductSnapshot:
    fields = dict(
        product_id=_UUID,
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
    fields.update(over)
    return ProductSnapshot(**fields)


def _created(version: int = 1) -> ProductCreatedEvent:
    return ProductCreatedEvent(
        event_id=UUID(int=1), occurred_at=NOW, product=_snapshot(version)
    )


def _content(version: int, name: str = "Наушники") -> ContentChangedEvent:
    return ContentChangedEvent(
        event_id=UUID(int=2),
        occurred_at=NOW,
        product_id=_UUID,
        sku="PROD-001",
        aggregate_version=version,
        changed_fields=("name",),
        name=name,
        description="Беспроводные",
        category="Электроника",
        brand="AudioMax",
    )


def _commercial(
    version: int, price: str = "119.99", stock: int = 230
) -> CommercialChangedEvent:
    return CommercialChangedEvent(
        event_id=UUID(int=3),
        occurred_at=NOW,
        product_id=_UUID,
        sku="PROD-001",
        aggregate_version=version,
        changed_fields=("price",),
        price=Decimal(price),
        cost=Decimal("65.00"),
        currency="RUB",
        stock=stock,
        supplier="TechSupply",
    )


def _deleted(version: int) -> ProductDeletedEvent:
    return ProductDeletedEvent(
        event_id=UUID(int=4),
        occurred_at=NOW,
        product_id=_UUID,
        sku="PROD-001",
        aggregate_version=version,
    )


def _wm_payload(version: int, content_hash: str | None = None) -> dict:
    return {
        "aggregate_version": version,
        "model_version": MODEL_KEY,
        "content_hash": content_hash,
        "indexed_at": NOW.isoformat(),
    }


def _hash(name: str = "Наушники") -> str:
    text = compose(
        name=name,
        brand="AudioMax",
        category="Электроника",
        description="Беспроводные",
    )
    return ContentHash.of(text.value).value


def _uc(index, embedder=None, catalog=None) -> ProcessCatalogEvent:
    return ProcessCatalogEvent(
        index=index,
        embedder=embedder or FakeEmbeddingModel(),
        catalog=catalog or FakeCatalogGateway(),
        clock=FixedClock(NOW),
    )


# --- created ---
async def test_created_full_index():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    action = await _uc(index, embedder).handle(_created(1))
    assert action is IndexingAction.FULL_INDEX
    assert embedder.calls == 1
    assert len(index.upserts) == 1
    payload = index.payload_of(PID)
    assert payload["price"] == 129.99
    assert payload["aggregate_version"] == 1
    assert payload["model_version"] == MODEL_KEY


async def test_created_stale_skipped():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(PID, _wm_payload(5))
    action = await _uc(index, embedder).handle(_created(4))
    assert action is IndexingAction.SKIP
    assert embedder.calls == 0
    assert index.upserts == []


# --- content_changed ---
async def test_content_reembeds():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    action = await _uc(index, embedder).handle(_content(6, name="Наушники Pro"))
    assert action is IndexingAction.REEMBED
    assert embedder.calls == 1
    assert index.vector_updates == [PID]
    payload = index.payload_of(PID)
    assert payload["name"] == "Наушники Pro"
    assert payload["aggregate_version"] == 6


async def test_content_unchanged_text_skips_reembed():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    action = await _uc(index, embedder).handle(_content(6))
    assert action is IndexingAction.PAYLOAD_ONLY
    assert embedder.calls == 0
    assert index.vector_updates == []
    assert index.payload_of(PID)["aggregate_version"] == 6


async def test_content_missing_point_repairs():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    catalog = FakeCatalogGateway([_snapshot(7)])
    action = await _uc(index, embedder, catalog).handle(_content(7))
    assert action is IndexingAction.REPAIR
    assert len(index.upserts) == 1
    assert embedder.calls == 1


async def test_repair_missing_in_catalog_raises():
    index = FakeVectorIndex()
    with pytest.raises(ProductNotInCatalog):
        await _uc(index, catalog=FakeCatalogGateway([])).handle(_content(7))


# --- commercial_data_changed ---
async def test_commercial_payload_only_no_embed():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(PID, _wm_payload(5))
    action = await _uc(index, embedder).handle(
        _commercial(6, price="119.99", stock=0)
    )
    assert action is IndexingAction.PAYLOAD_ONLY
    assert embedder.calls == 0
    assert index.vector_updates == []
    payload = index.payload_of(PID)
    assert payload["price"] == 119.99
    assert payload["in_stock"] is False
    assert "name" not in payload
    assert payload["aggregate_version"] == 6


async def test_commercial_stale_skipped():
    index = FakeVectorIndex()
    index.preload(PID, _wm_payload(6))
    assert await _uc(index).handle(_commercial(5)) is IndexingAction.SKIP


async def test_commercial_missing_point_repairs():
    index = FakeVectorIndex()
    catalog = FakeCatalogGateway([_snapshot(6)])
    action = await _uc(index, catalog=catalog).handle(_commercial(6))
    assert action is IndexingAction.REPAIR
    assert len(index.upserts) == 1


# --- deleted ---
async def test_deleted_tombstones():
    index = FakeVectorIndex()
    index.preload(PID, _wm_payload(5))
    action = await _uc(index).handle(_deleted(6))
    assert action is IndexingAction.TOMBSTONE
    payload = index.payload_of(PID)
    assert payload["is_deleted"] is True
    assert payload["aggregate_version"] == 6


async def test_deleted_missing_point_skipped():
    index = FakeVectorIndex()
    assert await _uc(index).handle(_deleted(6)) is IndexingAction.SKIP


async def test_late_content_after_tombstone_skipped():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(PID, {**_wm_payload(8), "is_deleted": True})
    action = await _uc(index, embedder).handle(_content(7))
    assert action is IndexingAction.SKIP
    assert embedder.calls == 0


# --- сиблинги одной версии (§6.2): merge без потерь ---
async def test_same_version_siblings_merge():
    index, embedder = FakeVectorIndex(), FakeEmbeddingModel()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    uc = _uc(index, embedder)
    await uc.handle(_commercial(6, price="119.99", stock=10))
    await uc.handle(_content(6, name="Наушники Pro"))
    payload = index.payload_of(PID)
    assert payload["price"] == 119.99
    assert payload["name"] == "Наушники Pro"
    assert payload["aggregate_version"] == 6
    assert index.vector_updates == [PID]


# --- poison ---
async def test_negative_stock_is_poison():
    index = FakeVectorIndex()
    index.preload(PID, _wm_payload(5))
    with pytest.raises(EventValidationError):
        await _uc(index).handle(_commercial(6, stock=-1))
