"""Тесты ``ReindexCatalog`` на job-модели (§8, Q6)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.use_cases.reindex_catalog import (
    ReindexCatalog,
)
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.domain.value_objects.job_status import JobStatus
from tests.support.fakes import (
    FakeCatalogGateway,
    FakeUnitOfWork,
    FakeVectorIndexAdmin,
    FixedClock,
)

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
TARGET = "products_v2"


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


def _reindex(admin, uow, catalog):
    clock = FixedClock(NOW)
    return ReindexCatalog(
        admin=admin,
        request_embedding=RequestEmbedding(
            uow,
            clock,
            chunker=SingleDocument(),
            expected_model=None,
            max_texts=32,
        ),
        uow=uow,
        catalog=catalog,
        clock=clock,
    )


async def test_execute_provisions_and_queues_jobs():
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1), _snapshot(2)])

    report = await _reindex(admin, uow, catalog).execute(
        target_collection=TARGET
    )

    assert report.queued == 2
    assert report.skipped == 0
    assert report.errors == 0
    assert admin.provisioned == [TARGET]
    # alias не трогаем: эпоха ещё не посчитана
    assert admin.swaps == []
    # карточки товаров легли в НОВУЮ коллекцию, а не в живой alias
    assert len(admin.writer(TARGET).payload_upserts) == 2
    assert admin.index.payload_upserts == []
    # на каждый товар — задание своей эпохи и команда в outbox
    assert len(uow.jobs.store) == 2
    assert all(
        job.target_collection == TARGET for job in uow.jobs.store.values()
    )
    assert len(uow.outbox.messages) == 2


async def test_rerun_of_epoch_is_idempotent():
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1)])
    reindex = _reindex(admin, uow, catalog)

    await reindex.execute(target_collection=TARGET)
    report = await reindex.execute(target_collection=TARGET)

    assert report.queued == 0
    assert report.skipped == 1
    assert len(uow.jobs.store) == 1


async def test_swap_waits_until_epoch_is_done():
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1), _snapshot(2)])
    reindex = _reindex(admin, uow, catalog)
    await reindex.execute(target_collection=TARGET)

    report = await reindex.swap(target_collection=TARGET, alias="products")

    assert report.swapped is False
    assert report.total == 2
    assert report.done == 0
    assert report.pending == 2
    assert admin.swaps == []


async def test_swap_happens_when_all_jobs_done():
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1), _snapshot(2)])
    reindex = _reindex(admin, uow, catalog)
    await reindex.execute(target_collection=TARGET)
    await _finish_all(uow, JobStatus.DONE)
    admin.ready_roots[TARGET] = 2  # векторы эпохи действительно на месте

    report = await reindex.swap(target_collection=TARGET, alias="products")

    assert report.swapped is True
    assert report.done == 2
    assert report.indexed == 2
    assert admin.swaps == [("products", TARGET)]


async def test_swap_blocked_when_target_collection_has_no_vectors():
    """Задания закрыты, но в целевой коллекции векторов нет → не свапаем.

    Ровно этот случай ловит баг маршрутизации: результаты эпохи ушли бы в
    живой alias, а alias переключился бы на коллекцию без векторов.
    """
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1), _snapshot(2)])
    reindex = _reindex(admin, uow, catalog)
    await reindex.execute(target_collection=TARGET)
    await _finish_all(uow, JobStatus.DONE)
    admin.ready_roots[TARGET] = 0

    report = await reindex.swap(target_collection=TARGET, alias="products")

    assert report.swapped is False
    assert report.done == 2
    assert report.indexed == 0
    assert admin.swaps == []


async def test_swap_blocked_when_vectors_lag_behind_done_jobs():
    """Частично долетевшая эпоха тоже не пускается в alias."""
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(1), _snapshot(2)])
    reindex = _reindex(admin, uow, catalog)
    await reindex.execute(target_collection=TARGET)
    await _finish_all(uow, JobStatus.DONE)
    admin.ready_roots[TARGET] = 1

    report = await reindex.swap(target_collection=TARGET, alias="products")

    assert report.swapped is False
    assert report.indexed == 1
    assert admin.swaps == []


async def test_threshold_allows_swap_with_stragglers():
    """Порог позволяет не ждать безнадёжно отставших (Q6)."""
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    catalog = FakeCatalogGateway([_snapshot(i) for i in range(1, 5)])
    reindex = _reindex(admin, uow, catalog)
    await reindex.execute(target_collection=TARGET)
    jobs = list(uow.jobs.store.values())
    await _set_status(uow, jobs[:3], JobStatus.DONE)
    await _set_status(uow, jobs[3:], JobStatus.FAILED)
    admin.ready_roots[TARGET] = 3

    strict = await reindex.swap(target_collection=TARGET, alias="products")
    lenient = await reindex.swap(
        target_collection=TARGET, alias="products", min_ready=0.75
    )

    assert strict.swapped is False
    assert lenient.swapped is True
    assert lenient.done == 3
    assert lenient.failed == 1


async def test_swap_of_unknown_epoch_does_nothing():
    admin, uow = FakeVectorIndexAdmin(), FakeUnitOfWork()
    reindex = _reindex(admin, uow, FakeCatalogGateway([]))

    report = await reindex.swap(target_collection=TARGET, alias="products")

    assert report.swapped is False
    assert report.total == 0
    assert admin.swaps == []


async def _finish_all(uow, status) -> None:
    await _set_status(uow, list(uow.jobs.store.values()), status)


async def _set_status(uow, jobs, status) -> None:
    from dataclasses import replace

    for job in jobs:
        await uow.jobs.upsert(replace(job, status=status))
