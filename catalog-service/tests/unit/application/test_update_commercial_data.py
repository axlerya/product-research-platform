"""Тесты use case ``UpdateCommercialData``."""

from decimal import Decimal
from uuid import UUID

import pytest

from catalog_service.application.dto.commands import (
    UpdateCommercialDataCommand,
)
from catalog_service.application.exceptions import (
    ProductNotFound,
    ValidationError,
)
from catalog_service.application.use_cases.update_commercial_data import (
    UpdateCommercialData,
)
from tests.support.factories import (
    FIXED_NOW,
    PRODUCT_ID,
    make_pricing,
    make_product,
)
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


def _uc(uow: FakeUnitOfWork) -> UpdateCommercialData:
    return UpdateCommercialData(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
    )


async def test_change_price_and_stock():
    uow = FakeUnitOfWork()
    uow.products.preload(
        make_product(pricing=make_pricing("129.99", "65.00"), version=1)
    )
    result = await _uc(uow).execute(
        UpdateCommercialDataCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            price_amount=Decimal("119.99"),
            stock_quantity=230,
        )
    )
    assert result.version == 2
    data = uow.outbox.messages[0].payload["data"]
    assert data["changed_fields"] == ["price", "stock"]
    assert data["price"]["amount"] == "119.99"


async def test_partial_price_preserves_cost():
    uow = FakeUnitOfWork()
    uow.products.preload(
        make_product(pricing=make_pricing("129.99", "65.00"), version=1)
    )
    await _uc(uow).execute(
        UpdateCommercialDataCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            price_amount=Decimal("119.99"),
        )
    )
    data = uow.outbox.messages[0].payload["data"]
    assert data["changed_fields"] == ["price"]
    assert data["cost"]["amount"] == "65.00"


async def test_negative_stock_raises_validation():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1))
    with pytest.raises(ValidationError):
        await _uc(uow).execute(
            UpdateCommercialDataCommand(
                product_id=PRODUCT_ID.value,
                expected_version=1,
                stock_quantity=-5,
            )
        )


async def test_not_found_raises():
    uow = FakeUnitOfWork()
    with pytest.raises(ProductNotFound):
        await _uc(uow).execute(
            UpdateCommercialDataCommand(
                product_id=UUID(int=999),
                expected_version=1,
                stock_quantity=10,
            )
        )


async def test_change_cost_only():
    uow = FakeUnitOfWork()
    uow.products.preload(
        make_product(pricing=make_pricing("129.99", "65.00"), version=1)
    )
    await _uc(uow).execute(
        UpdateCommercialDataCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            cost_amount=Decimal("70.00"),
        )
    )
    data = uow.outbox.messages[0].payload["data"]
    assert data["changed_fields"] == ["cost"]
    assert data["cost"]["amount"] == "70.00"


async def test_change_supplier_only():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1))
    result = await _uc(uow).execute(
        UpdateCommercialDataCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            supplier_name="НовыйПоставщик",
        )
    )
    assert result.version == 2
    data = uow.outbox.messages[0].payload["data"]
    assert data["changed_fields"] == ["supplier"]
    assert data["supplier"] == "НовыйПоставщик"
