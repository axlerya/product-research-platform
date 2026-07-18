"""Тесты use case ``UpdateMetrics`` (версия растёт, событий нет)."""

from decimal import Decimal
from uuid import UUID

import pytest

from catalog_service.application.dto.commands import UpdateMetricsCommand
from catalog_service.application.exceptions import (
    ProductNotFound,
    ValidationError,
)
from catalog_service.application.use_cases.update_metrics import (
    UpdateMetrics,
)
from tests.support.factories import (
    FIXED_NOW,
    PRODUCT_ID,
    make_metrics,
    make_product,
)
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


def _uc(uow: FakeUnitOfWork) -> UpdateMetrics:
    return UpdateMetrics(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
    )


async def test_bumps_version_without_outbox():
    uow = FakeUnitOfWork()
    uow.products.preload(
        make_product(metrics=make_metrics(sales=87), version=1)
    )
    result = await _uc(uow).execute(
        UpdateMetricsCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            sales_per_month=999,
            avg_rating=Decimal("4.5"),
            review_count=1243,
        )
    )
    assert uow.committed is True
    assert result.version == 2
    assert result.emitted_events == ()
    assert uow.outbox.messages == []


async def test_no_diff_is_noop():
    uow = FakeUnitOfWork()
    uow.products.preload(
        make_product(
            metrics=make_metrics(sales=87, rating="4.50", reviews=1243),
            version=1,
        )
    )
    result = await _uc(uow).execute(
        UpdateMetricsCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            sales_per_month=87,
            avg_rating=Decimal("4.50"),
            review_count=1243,
        )
    )
    assert result.version == 1
    assert uow.outbox.messages == []


async def test_invalid_rating_raises_validation():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1))
    with pytest.raises(ValidationError):
        await _uc(uow).execute(
            UpdateMetricsCommand(
                product_id=PRODUCT_ID.value,
                expected_version=1,
                sales_per_month=1,
                avg_rating=Decimal("9"),
                review_count=1,
            )
        )


async def test_not_found_raises():
    uow = FakeUnitOfWork()
    with pytest.raises(ProductNotFound):
        await _uc(uow).execute(
            UpdateMetricsCommand(
                product_id=UUID(int=999),
                expected_version=1,
                sales_per_month=1,
                avg_rating=Decimal("4"),
                review_count=1,
            )
        )
