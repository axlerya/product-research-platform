"""Тесты use case ``UpdateProductContent``."""

from uuid import UUID

import pytest

from catalog_service.application.dto.commands import (
    UpdateProductContentCommand,
)
from catalog_service.application.exceptions import (
    ConcurrencyConflict,
    ProductNotFound,
)
from catalog_service.application.use_cases.update_product_content import (
    UpdateProductContent,
)
from tests.support.factories import FIXED_NOW, PRODUCT_ID, make_product
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


def _uc(uow: FakeUnitOfWork) -> UpdateProductContent:
    return UpdateProductContent(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
    )


async def test_change_name_emits_content_changed():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(name="Наушники", version=1))
    result = await _uc(uow).execute(
        UpdateProductContentCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            name="Новое имя",
        )
    )
    assert uow.committed is True
    assert result.version == 2
    assert result.emitted_events == ("catalog.product.content_changed",)
    data = uow.outbox.messages[0].payload["data"]
    assert data["changed_fields"] == ["name"]


async def test_no_diff_is_noop_without_event():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(name="Наушники", version=1))
    result = await _uc(uow).execute(
        UpdateProductContentCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            name="Наушники",
        )
    )
    assert uow.committed is True
    assert result.version == 1
    assert result.emitted_events == ()
    assert uow.outbox.messages == []


async def test_not_found_raises():
    uow = FakeUnitOfWork()
    with pytest.raises(ProductNotFound):
        await _uc(uow).execute(
            UpdateProductContentCommand(
                product_id=UUID(int=999),
                expected_version=1,
                name="X",
            )
        )


async def test_stale_version_raises_conflict():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=3))
    with pytest.raises(ConcurrencyConflict):
        await _uc(uow).execute(
            UpdateProductContentCommand(
                product_id=PRODUCT_ID.value,
                expected_version=2,
                name="X",
            )
        )


async def test_change_category_and_brand():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1))
    result = await _uc(uow).execute(
        UpdateProductContentCommand(
            product_id=PRODUCT_ID.value,
            expected_version=1,
            category_name="Гаджеты",
            brand_name="SoundPro",
        )
    )
    assert result.version == 2
    data = uow.outbox.messages[0].payload["data"]
    assert set(data["changed_fields"]) == {"category", "brand"}
    assert data["category"] == "Гаджеты"
    assert data["brand"] == "SoundPro"
