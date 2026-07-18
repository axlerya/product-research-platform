"""Тесты use case ``SeedCatalog`` (идемпотентный seed из CSV)."""

from collections.abc import Iterator

from catalog_service.application.dto.seed import RawProductRow
from catalog_service.application.use_cases.seed_catalog import SeedCatalog
from tests.support.factories import FIXED_NOW
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


class FakeCsvRowSource:
    """In-memory источник строк CSV."""

    def __init__(self, rows: list[RawProductRow]) -> None:
        self._rows = rows

    def __iter__(self) -> Iterator[RawProductRow]:
        return iter(self._rows)


def raw_row(line_no: int = 2, **over) -> RawProductRow:
    base = {
        "sku": "PROD-001",
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
    return RawProductRow(line_no=line_no, **base)


def _uc(
    uow: FakeUnitOfWork,
    source: FakeCsvRowSource,
    on_stale: str = "skip",
) -> SeedCatalog:
    return SeedCatalog(
        uow=uow,
        source=source,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
        default_currency="RUB",
        on_stale=on_stale,
    )


async def test_first_run_creates_all():
    uow = FakeUnitOfWork()
    rows = [raw_row(sku="PROD-1", line_no=2), raw_row(sku="PROD-2", line_no=3)]
    report = await _uc(uow, FakeCsvRowSource(rows)).execute()
    assert report.total == 2
    assert report.created == 2
    assert report.events_emitted == 2
    assert len(uow.outbox.messages) == 2
    assert uow.committed is True


async def test_rerun_is_idempotent():
    uow = FakeUnitOfWork()
    rows = [raw_row(sku="PROD-1"), raw_row(sku="PROD-2")]
    await _uc(uow, FakeCsvRowSource(rows)).execute()
    uow.outbox.messages.clear()
    report2 = await _uc(uow, FakeCsvRowSource(rows)).execute()
    assert report2.created == 0
    assert report2.events_emitted == 0
    assert uow.outbox.messages == []


async def test_overwrite_rerun_is_unchanged():
    uow = FakeUnitOfWork()
    rows = [raw_row(sku="PROD-1")]
    await _uc(uow, FakeCsvRowSource(rows), on_stale="overwrite").execute()
    uow.outbox.messages.clear()
    report2 = await _uc(
        uow, FakeCsvRowSource(rows), on_stale="overwrite"
    ).execute()
    assert report2.unchanged == 1
    assert report2.events_emitted == 0


async def test_changed_content_with_newer_date():
    uow = FakeUnitOfWork()
    await _uc(
        uow,
        FakeCsvRowSource(
            [raw_row(sku="PROD-1", source_updated_at="2024-03-15")]
        ),
    ).execute()
    uow.outbox.messages.clear()
    report2 = await _uc(
        uow,
        FakeCsvRowSource(
            [
                raw_row(
                    sku="PROD-1",
                    name="Новое имя",
                    source_updated_at="2024-04-01",
                )
            ]
        ),
    ).execute()
    assert report2.content_changed == 1
    assert report2.events_emitted == 1
    assert (
        uow.outbox.messages[0].event_type == "catalog.product.content_changed"
    )


async def test_changed_commercial_with_newer_date():
    uow = FakeUnitOfWork()
    await _uc(uow, FakeCsvRowSource([raw_row(sku="PROD-1")])).execute()
    uow.outbox.messages.clear()
    report2 = await _uc(
        uow,
        FakeCsvRowSource(
            [
                raw_row(
                    sku="PROD-1", price="119.99", source_updated_at="2024-05-01"
                )
            ]
        ),
    ).execute()
    assert report2.commercial_changed == 1
    assert report2.events_emitted == 1


async def test_both_groups_changed():
    uow = FakeUnitOfWork()
    await _uc(uow, FakeCsvRowSource([raw_row(sku="PROD-1")])).execute()
    uow.outbox.messages.clear()
    report2 = await _uc(
        uow,
        FakeCsvRowSource(
            [
                raw_row(
                    sku="PROD-1",
                    name="Имя2",
                    price="119.99",
                    source_updated_at="2024-05-01",
                )
            ]
        ),
    ).execute()
    assert report2.both == 1
    assert report2.events_emitted == 2


async def test_metrics_only_change_has_no_event():
    uow = FakeUnitOfWork()
    await _uc(uow, FakeCsvRowSource([raw_row(sku="PROD-1")])).execute()
    uow.outbox.messages.clear()
    report2 = await _uc(
        uow,
        FakeCsvRowSource(
            [
                raw_row(
                    sku="PROD-1",
                    sales_per_month="999",
                    source_updated_at="2024-05-01",
                )
            ]
        ),
    ).execute()
    assert report2.metrics_only == 1
    assert report2.events_emitted == 0


async def test_no_source_date_is_not_skipped():
    uow = FakeUnitOfWork()
    await _uc(
        uow, FakeCsvRowSource([raw_row(sku="PROD-1", source_updated_at=None)])
    ).execute()
    uow.outbox.messages.clear()
    report2 = await _uc(
        uow,
        FakeCsvRowSource(
            [raw_row(sku="PROD-1", name="Новое", source_updated_at=None)]
        ),
    ).execute()
    assert report2.content_changed == 1


async def test_bad_price_is_recorded_not_crashing():
    uow = FakeUnitOfWork()
    rows = [
        raw_row(sku="PROD-1"),
        raw_row(sku="PROD-2", price="abc"),
        raw_row(sku="PROD-3"),
    ]
    report = await _uc(uow, FakeCsvRowSource(rows)).execute()
    assert report.total == 3
    assert report.created == 2
    assert len(report.errors) == 1
    assert report.errors[0].kind == "parse"


async def test_negative_price_is_domain_error():
    uow = FakeUnitOfWork()
    report = await _uc(
        uow, FakeCsvRowSource([raw_row(sku="PROD-1", price="-5")])
    ).execute()
    assert report.created == 0
    assert report.errors[0].kind == "domain"


async def test_empty_required_field_is_error():
    uow = FakeUnitOfWork()
    report = await _uc(
        uow, FakeCsvRowSource([raw_row(sku="PROD-1", name=None)])
    ).execute()
    assert report.created == 0
    assert report.errors[0].kind == "parse"


async def test_duplicate_sku_in_file_is_error():
    uow = FakeUnitOfWork()
    rows = [raw_row(sku="PROD-1"), raw_row(sku="PROD-1", line_no=3)]
    report = await _uc(uow, FakeCsvRowSource(rows)).execute()
    assert report.created == 1
    assert len(report.errors) == 1
    assert report.errors[0].kind == "duplicate_in_file"
