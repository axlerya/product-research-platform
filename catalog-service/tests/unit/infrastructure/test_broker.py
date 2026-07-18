"""Тесты publisher событий через ``TestRabbitBroker`` (без RabbitMQ)."""

from faststream.rabbit import RabbitQueue, TestRabbitBroker

from catalog_service.infrastructure.config import Settings
from catalog_service.infrastructure.messaging.broker import (
    CATALOG_EVENTS,
    RabbitEventPublisher,
    build_broker,
)


async def test_publishes_to_topic_exchange():
    broker = build_broker(Settings())
    received: list = []

    @broker.subscriber(
        RabbitQueue("t_created", routing_key="catalog.product.created"),
        CATALOG_EVENTS,
    )
    async def _handler(body: dict) -> None:
        received.append(body)

    async with TestRabbitBroker(broker):
        await RabbitEventPublisher(broker).publish(
            {"event_type": "catalog.product.created"},
            routing_key="catalog.product.created",
            message_id="m1",
            headers={},
        )

    assert received == [{"event_type": "catalog.product.created"}]
