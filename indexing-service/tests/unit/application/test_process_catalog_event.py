"""Тесты оркестратора ``ProcessCatalogEvent`` на in-memory фейках (§6).

Проверяют все ветки действий, merge-семантику сиблингов одной версии,
gap-repair, дедуп ре-эмбеддинга, защиту от воскрешения и poison.

После cutover (шаг 5) ветки created/content/repair векторы не считают: они
пишут карточку товара и ставят задание через ``RequestEmbedding``. Поэтому
здесь же проверяется, что job и команда действительно появляются.
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
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.change_classifier import IndexingAction
from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import IndexAction
from tests.support.fakes import (
    FakeCatalogGateway,
    FakeUnitOfWork,
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


def _uc(
    index, uow=None, catalog=None, *, expected_model=None
) -> ProcessCatalogEvent:
    clock = FixedClock(NOW)
    return ProcessCatalogEvent(
        index=index,
        request_embedding=RequestEmbedding(
            uow if uow is not None else FakeUnitOfWork(),
            clock,
            chunker=SingleDocument(),
            expected_model=expected_model,
            max_texts=32,
        ),
        catalog=catalog or FakeCatalogGateway(),
        clock=clock,
        expected_model=expected_model,
    )


# --- created ---
async def test_created_writes_card_and_requests_embedding():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    action = await _uc(index, uow).handle(_created(1))

    assert action is IndexingAction.FULL_INDEX
    # карточка товара видна фильтрам сразу, векторов ещё нет
    assert len(index.payload_upserts) == 1
    payload = index.payload_of(PID)
    assert payload["price"] == 129.99
    assert payload["aggregate_version"] == 1
    # задание поставлено, команда лежит в outbox
    [job] = list(uow.jobs.store.values())
    assert job.action is IndexAction.FULL_INDEX
    assert job.content_version == 1
    assert len(uow.outbox.messages) == 1
    assert uow.commits == 1


async def test_created_does_not_claim_text_is_indexed():
    """Водяные знаки ставит только тот, кто посчитал векторы (§9.4)."""
    index = FakeVectorIndex()
    await _uc(index).handle(_created(1))

    payload = index.payload_of(PID)
    assert "content_hash" not in payload
    assert "model_version" not in payload


async def test_created_stale_skipped():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5))
    action = await _uc(index, uow).handle(_created(4))
    assert action is IndexingAction.SKIP
    assert index.payload_upserts == []
    assert uow.jobs.store == {}


# --- content_changed ---
async def test_content_requests_reembedding():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    action = await _uc(index, uow).handle(_content(6, name="Наушники Pro"))

    assert action is IndexingAction.REEMBED
    assert index.vector_updates == []  # векторы посчитает embedding-service
    payload = index.payload_of(PID)
    assert payload["name"] == "Наушники Pro"
    assert payload["aggregate_version"] == 6
    [job] = list(uow.jobs.store.values())
    assert job.action is IndexAction.REEMBED
    assert job.content_version == 6
    assert job.content_hash == ContentHash.of(
        compose(
            name="Наушники Pro",
            brand="AudioMax",
            category="Электроника",
            description="Беспроводные",
        ).value
    )
    assert len(uow.outbox.messages) == 1


async def test_content_redelivery_does_not_duplicate_job():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    use_case = _uc(index, uow)

    await use_case.handle(_content(6, name="Наушники Pro"))
    await use_case.handle(_content(6, name="Наушники Pro"))

    assert len(uow.jobs.store) == 1
    assert len(uow.outbox.messages) == 1


async def test_content_unchanged_text_skips_reembed():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    action = await _uc(index, uow).handle(_content(6))

    assert action is IndexingAction.PAYLOAD_ONLY
    assert uow.jobs.store == {}
    assert uow.outbox.messages == []
    assert index.payload_of(PID)["aggregate_version"] == 6
    # дедуп не должен сбивать уже стоящие водяные знаки
    assert index.payload_of(PID)["content_hash"] == _hash()
    assert index.payload_of(PID)["model_version"] == MODEL_KEY


async def test_content_missing_point_repairs():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(7)])
    action = await _uc(index, uow, catalog).handle(_content(7))

    assert action is IndexingAction.REPAIR
    assert len(index.payload_upserts) == 1
    assert len(uow.jobs.store) == 1


async def test_repair_missing_in_catalog_raises():
    index = FakeVectorIndex()
    with pytest.raises(ProductNotInCatalog):
        await _uc(index, catalog=FakeCatalogGateway([])).handle(_content(7))


# --- commercial_data_changed ---
async def test_commercial_payload_only_no_job():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5))
    action = await _uc(index, uow).handle(
        _commercial(6, price="119.99", stock=0)
    )
    assert action is IndexingAction.PAYLOAD_ONLY
    assert uow.jobs.store == {}
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
    assert len(index.payload_upserts) == 1


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
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, {**_wm_payload(8), "is_deleted": True})
    action = await _uc(index, uow).handle(_content(7))
    assert action is IndexingAction.SKIP
    assert uow.jobs.store == {}


# --- сиблинги одной версии (§6.2): merge без потерь ---
async def test_same_version_siblings_merge():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    uc = _uc(index, uow)
    await uc.handle(_commercial(6, price="119.99", stock=10))
    await uc.handle(_content(6, name="Наушники Pro"))
    payload = index.payload_of(PID)
    assert payload["price"] == 119.99
    assert payload["name"] == "Наушники Pro"
    assert payload["aggregate_version"] == 6
    assert len(uow.jobs.store) == 1


async def test_pinned_model_drift_forces_reembed():
    """Закреплённая модель разошлась с точкой → пересчёт (§6.2)."""
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(PID, _wm_payload(5, content_hash=_hash()))
    action = await _uc(index, uow, expected_model="другая-модель").handle(
        _content(6)
    )
    assert action is IndexingAction.REEMBED
    assert len(uow.jobs.store) == 1


# --- poison ---
async def test_negative_stock_is_poison():
    index = FakeVectorIndex()
    index.preload(PID, _wm_payload(5))
    with pytest.raises(EventValidationError):
        await _uc(index).handle(_commercial(6, stock=-1))


# --- многочанковый товар: payload обязан лечь на ВСЕ точки ---


def _preload_multichunk(index, version: int, **root) -> None:
    """Корневая точка + две чанк-точки того же товара (после rechunk)."""
    index.preload(
        PID, {**_wm_payload(version, **root), "product_id": str(_UUID)}
    )
    for chunk_ix in (1, 2):
        index.preload_chunk(PID, chunk_ix, _wm_payload(version))


async def test_commercial_update_reaches_every_chunk():
    """Цена и наличие обязаны совпадать на всех чанках товара.

    Иначе фильтр по цене/остатку отсечёт чанки > 0, и товар потеряет часть
    своих векторов в выдаче.
    """
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    _preload_multichunk(index, 5)

    await _uc(index, uow).handle(_commercial(6, price="119.99", stock=0))

    chunks = index.chunk_payloads(PID)
    assert len(chunks) == 2
    for payload in (index.payload_of(PID), *chunks):
        assert payload["price"] == 119.99
        assert payload["in_stock"] is False
        assert payload["aggregate_version"] == 6


async def test_delete_tombstones_every_chunk():
    """Удаление товара обязано снять с поиска все его точки."""
    index = FakeVectorIndex()
    _preload_multichunk(index, 5)

    await _uc(index).handle(_deleted(6))

    chunks = index.chunk_payloads(PID)
    assert len(chunks) == 2
    for payload in (index.payload_of(PID), *chunks):
        assert payload["is_deleted"] is True
        assert payload["aggregate_version"] == 6


async def test_content_fields_reach_every_chunk():
    """Текстовые поля и рейтинг тоже разъезжаются по всем точкам."""
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    _preload_multichunk(index, 5, content_hash=_hash())

    await _uc(index, uow).handle(_content(6, name="Наушники Pro"))

    for payload in (index.payload_of(PID), *index.chunk_payloads(PID)):
        assert payload["name"] == "Наушники Pro"
        assert payload["aggregate_version"] == 6
