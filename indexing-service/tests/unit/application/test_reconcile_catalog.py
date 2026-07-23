"""Тесты ``ReconcileCatalog`` на job-модели (§9).

Reconcile векторы не считает: где нужен пересчёт, он ставит задание, а не
эмбеддит на месте. Поэтому «починено» проверяется по появлению job.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.use_cases.reconcile_catalog import (
    ReconcileCatalog,
)
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from tests.support.fakes import (
    FakeCatalogGateway,
    FakeUnitOfWork,
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


def _reconcile(index, uow, catalog, *, expected_model=None):
    clock = FixedClock(NOW)
    return ReconcileCatalog(
        index=index,
        request_embedding=RequestEmbedding(
            uow,
            clock,
            chunker=SingleDocument(),
            expected_model=expected_model,
            max_texts=32,
        ),
        catalog=catalog,
        clock=clock,
        expected_model=expected_model,
    )


async def test_missing_is_queued_for_embedding():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1, 1)])

    report = await _reconcile(index, uow, catalog).execute()

    assert report.indexed == 1
    assert index.exists(ProductId(UUID(int=1)))
    assert len(uow.jobs.store) == 1
    assert len(uow.outbox.messages) == 1


async def test_up_to_date_matched():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash()))

    report = await _reconcile(
        index, uow, FakeCatalogGateway([_snapshot(1, 5)])
    ).execute()

    assert report.matched == 1
    assert uow.jobs.store == {}


async def test_metrics_drift_repaired_without_job():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash()))
    catalog = FakeCatalogGateway([_snapshot(1, 6)])  # версия бумпнута

    report = await _reconcile(index, uow, catalog).execute()

    assert report.repaired == 1
    assert uow.jobs.store == {}  # текст тот же — пересчёт не нужен
    payload = index.payload_of(ProductId(UUID(int=1)))
    assert payload["aggregate_version"] == 6
    # водяные знаки не сбиты: векторы по-прежнему актуальны
    assert payload["content_hash"] == _hash()
    assert payload["model_version"] == MODEL_KEY


async def test_text_drift_queues_reembedding():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash("Наушники")))
    catalog = FakeCatalogGateway([_snapshot(1, 6, name="Новое имя")])

    report = await _reconcile(index, uow, catalog).execute()

    assert report.repaired == 1
    assert len(uow.jobs.store) == 1
    assert len(uow.outbox.messages) == 1


async def test_model_drift_queues_reembedding():
    """Дрейф закреплённой модели → пересчёт векторов (§10)."""
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(ProductId(UUID(int=1)), _wm(5, _hash()))
    catalog = FakeCatalogGateway([_snapshot(1, 5)])

    report = await _reconcile(
        index, uow, catalog, expected_model="другая-модель"
    ).execute()

    assert report.repaired == 1
    assert len(uow.jobs.store) == 1


async def test_orphan_tombstoned():
    index, uow = FakeVectorIndex(), FakeUnitOfWork()
    index.preload(ProductId(UUID(int=9)), _wm(3, None))

    report = await _reconcile(index, uow, FakeCatalogGateway([])).execute()

    assert report.tombstoned == 1
    assert index.payload_of(ProductId(UUID(int=9)))["is_deleted"] is True
    assert uow.jobs.store == {}
