"""Тесты use case ``CreateProduct``."""

from decimal import Decimal

import pytest

from catalog_service.application.dto.commands import CreateProductCommand
from catalog_service.application.exceptions import (
    DuplicateSku,
    ValidationError,
)
from catalog_service.application.use_cases.create_product import (
    CreateProduct,
)
from catalog_service.domain.value_objects.sku import Sku
from tests.support.factories import FIXED_NOW, PRODUCT_ID
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


def _cmd(**over) -> CreateProductCommand:
    base = {
        "sku": "PROD-100",
        "name": "Товар",
        "description": "Опис",
        "category_name": "Электроника",
        "brand_name": "AudioMax",
        "supplier_name": "TechSupply Co",
        "price_amount": Decimal("129.99"),
        "cost_amount": Decimal("65.00"),
        "stock_quantity": 245,
        "sales_per_month": 87,
        "avg_rating": Decimal("4.5"),
        "review_count": 1243,
    }
    base.update(over)
    return CreateProductCommand(**base)


def _uc(uow: FakeUnitOfWork) -> CreateProduct:
    return CreateProduct(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(product_ids=[PRODUCT_ID]),
        default_currency="RUB",
    )


async def test_creates_product_and_emits_created():
    uow = FakeUnitOfWork()
    result = await _uc(uow).execute(_cmd())

    assert uow.committed is True
    assert result.version == 1
    assert result.emitted_events == ("catalog.product.created",)
    assert len(uow.outbox.messages) == 1
    assert uow.outbox.messages[0].event_type == "catalog.product.created"
    assert await uow.products.get_by_sku(Sku("PROD-100")) is not None


async def test_duplicate_sku_raises():
    uow = FakeUnitOfWork()
    await _uc(uow).execute(_cmd(sku="PROD-1"))
    duplicate_uc = CreateProduct(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
        default_currency="RUB",
    )
    with pytest.raises(DuplicateSku):
        await duplicate_uc.execute(_cmd(sku="PROD-1"))


async def test_invalid_sku_raises_validation():
    with pytest.raises(ValidationError):
        await _uc(FakeUnitOfWork()).execute(_cmd(sku="!"))


async def test_negative_price_raises_validation():
    with pytest.raises(ValidationError):
        await _uc(FakeUnitOfWork()).execute(_cmd(price_amount=Decimal("-1")))
