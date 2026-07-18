"""Integration-тесты outbox-relay на реальном Postgres."""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from catalog_service.application.dto.commands import CreateProductCommand
from catalog_service.application.use_cases.create_product import CreateProduct
from catalog_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from catalog_service.infrastructure.outbox.relay import OutboxPublisher
from catalog_service.infrastructure.services.clock import SystemClock
from catalog_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)

pytestmark = pytest.mark.integration


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list = []
        self._fail = fail

    async def publish(
        self, payload, *, routing_key, message_id, headers
    ) -> None:
        self.calls.append((routing_key, message_id))
        if self._fail:
            raise RuntimeError("broker down")


def _cmd(index: int) -> CreateProductCommand:
    return CreateProductCommand(
        sku=f"PROD-{index}",
        name="Наушники",
        description="Опис",
        category_name="Электроника",
        brand_name="AudioMax",
        supplier_name="TechSupply Co",
        price_amount=Decimal("129.99"),
        cost_amount=Decimal("65.00"),
        stock_quantity=245,
        sales_per_month=87,
        avg_rating=Decimal("4.5"),
        review_count=1243,
    )


async def _seed(sm: async_sessionmaker, count: int) -> None:
    for index in range(count):
        await CreateProduct(
            uow=SqlAlchemyUnitOfWork(sm),
            clock=SystemClock(),
            id_gen=Uuid7Generator(),
            default_currency="RUB",
        ).execute(_cmd(index))


async def _one(sm: async_sessionmaker, sql: str):
    async with sm() as session:
        return (await session.execute(text(sql))).first()


async def test_drain_publishes_and_marks(sm):
    await _seed(sm, 2)
    publisher = _FakePublisher()
    relay = OutboxPublisher(sm, publisher)

    assert await relay.drain_all() == 2
    assert len(publisher.calls) == 2
    assert all(rk == "catalog.product.created" for rk, _ in publisher.calls)

    row = await _one(
        sm, "SELECT count(*) AS c FROM outbox WHERE published_at IS NULL"
    )
    assert row.c == 0
    assert await relay.drain_all() == 0


async def test_failure_sets_backoff(sm):
    await _seed(sm, 1)
    relay = OutboxPublisher(sm, _FakePublisher(fail=True), max_attempts=10)

    await relay.drain_batch()

    row = await _one(
        sm,
        "SELECT published_at, attempts, next_attempt_at, failed_at FROM outbox",
    )
    assert row.published_at is None
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert row.failed_at is None


async def test_failed_after_max_attempts(sm):
    await _seed(sm, 1)
    relay = OutboxPublisher(sm, _FakePublisher(fail=True), max_attempts=1)

    await relay.drain_batch()

    row = await _one(sm, "SELECT failed_at FROM outbox")
    assert row.failed_at is not None
