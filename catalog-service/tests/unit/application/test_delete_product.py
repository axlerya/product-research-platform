"""Тесты use case ``DeleteProduct`` (soft-delete, идемпотентно)."""

from uuid import UUID

import pytest

from catalog_service.application.dto.commands import DeleteProductCommand
from catalog_service.application.exceptions import ProductNotFound
from catalog_service.application.use_cases.delete_product import (
    DeleteProduct,
)
from tests.support.factories import FIXED_NOW, PRODUCT_ID, make_product
from tests.support.fakes import (
    FakeUnitOfWork,
    FixedClock,
    SequenceIdGenerator,
)


def _uc(uow: FakeUnitOfWork) -> DeleteProduct:
    return DeleteProduct(
        uow=uow,
        clock=FixedClock(FIXED_NOW),
        id_gen=SequenceIdGenerator(),
    )


async def test_delete_emits_deleted():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1))
    result = await _uc(uow).execute(
        DeleteProductCommand(product_id=PRODUCT_ID.value, expected_version=1)
    )
    assert result.version == 2
    assert result.emitted_events == ("catalog.product.deleted",)
    assert uow.outbox.messages[0].event_type == "catalog.product.deleted"


async def test_delete_is_idempotent():
    uow = FakeUnitOfWork()
    uow.products.preload(make_product(version=1, is_deleted=True))
    result = await _uc(uow).execute(
        DeleteProductCommand(product_id=PRODUCT_ID.value, expected_version=1)
    )
    assert result.version == 1
    assert result.emitted_events == ()
    assert uow.outbox.messages == []


async def test_not_found_raises():
    uow = FakeUnitOfWork()
    with pytest.raises(ProductNotFound):
        await _uc(uow).execute(
            DeleteProductCommand(product_id=UUID(int=999), expected_version=1)
        )
