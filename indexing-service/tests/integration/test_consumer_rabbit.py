"""Integration: доставка и топология консюмера против реального RabbitMQ."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from faststream.rabbit import RabbitBroker, TestRabbitBroker

from indexing_service.presentation.messaging.schemas import CatalogEnvelope
from indexing_service.presentation.messaging.topology import (
    CATALOG_EXCHANGE,
    PARKING_EXCHANGE,
    REQUEUE_EXCHANGE,
    RETRY_EXCHANGE,
    main_queue,
    parking_queue,
    retry_queue,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
_ENVELOPE = {
    "event_id": str(UUID(int=2)),
    "event_type": "catalog.product.deleted",
    "aggregate_id": str(UUID(int=1)),
    "sku": "PROD-001",
    "aggregate_version": 1,
    "occurred_at": _NOW.isoformat(),
    "data": {"product_id": str(UUID(int=1)), "sku": "PROD-001"},
}


async def test_real_delivery_and_retry_topology(rabbitmq_url):
    received: list[str] = []
    broker = RabbitBroker(rabbitmq_url)

    @broker.subscriber(main_queue(), CATALOG_EXCHANGE)
    async def handler(envelope: CatalogEnvelope) -> None:
        received.append(envelope.event_type)

    async with TestRabbitBroker(broker, with_real=True):
        # Топология retry/parking + bindings — как в consumer_app.after_startup;
        # проверяет, что declare/bind проходят против реального RabbitMQ.
        retry_ex = await broker.declare_exchange(RETRY_EXCHANGE)
        parking_ex = await broker.declare_exchange(PARKING_EXCHANGE)
        await broker.declare_exchange(REQUEUE_EXCHANGE)
        retry_q = await broker.declare_queue(retry_queue(30000))
        parking_q = await broker.declare_queue(parking_queue())
        await retry_q.bind(retry_ex, routing_key="catalog.product.*")
        await parking_q.bind(parking_ex, routing_key="catalog.product.*")

        await broker.publish(
            _ENVELOPE,
            exchange=CATALOG_EXCHANGE,
            routing_key="catalog.product.deleted",
        )
        await handler.wait_call(timeout=5)

    assert received == ["catalog.product.deleted"]
