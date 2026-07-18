"""Тесты use case ``SetStock`` (абсолютная установка остатка)."""

from uuid import UUID

import pytest

from catalog_service.application.dto.commands import SetStockCommand
from catalog_service.application.exceptions import (
    ProductNotFound,
    ValidationError,
)
from catalog_service.application.use_cases.set_stock import SetStock
from tests.support.factories import FIXED_NOW, PRODUCT_ID, make_product
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


def _uc(uow: FakeUnitOfWork) -> SetStock:
    return SetStock(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
    )


async def test_sets_stock_emits_commercial():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(stock=245, version=1))
    result = await _uc(uow).execute(
        SetStockCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            stock_quantity=300,
        )
    )
    assert result.version == 2
    data = uow.outbox.messages[0].payload["data"]
    assert data["changed_fields"] == ["stock"]
    assert data["stock"] == 300


async def test_negative_stock_raises_validation():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1))
    with pytest.raises(ValidationError):
        await _uc(uow).execute(
            SetStockCommand(
                product_id=PRODUCT_ID.value,
                expected_version=1,
                stock_quantity=-1,
            )
        )


async def test_not_found_raises():
    uow = FakeUnitOfWork()
    with pytest.raises(ProductNotFound):
        await _uc(uow).execute(
            SetStockCommand(
                product_id=UUID(int=999),
                expected_version=1,
                stock_quantity=10,
            )
        )
