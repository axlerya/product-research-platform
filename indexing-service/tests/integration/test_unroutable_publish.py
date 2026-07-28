"""Integration: publish в exchange без подходящей очереди — это неудача.

Сам по себе publish возврат сообщения брокером ошибкой не считает: он
отдаёт подтверждение с ``Basic.Return`` внутри. Если relay примет это за
успех, он пометит команду опубликованной, и она исчезнет бесследно — так
терялись задания на эмбеддинг, пока embedding-service не объявил очередь.
Проверяем на настоящем брокере, что публикация действительно падает.
"""

import pytest
from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

from indexing_service.infrastructure.config import Settings
from indexing_service.infrastructure.messaging.broker import (
    EMBEDDING_JOBS,
    RabbitEmbeddingPublisher,
    build_broker,
)

pytestmark = pytest.mark.integration

_ROUTING_KEY = "embedding.documents.requested.v1"
_QUEUE = RabbitQueue(
    "test.unroutable.consumer", durable=False, routing_key=_ROUTING_KEY
)


async def _publish(broker) -> None:
    await RabbitEmbeddingPublisher(broker).publish(
        {"event_type": _ROUTING_KEY},
        routing_key=_ROUTING_KEY,
        message_id="m1",
        headers={},
    )


async def test_publish_without_bound_queue_raises(rabbitmq_url: str) -> None:
    """Некому доставить — публикация обязана упасть, а не «успеть»."""
    broker = build_broker(Settings(rabbitmq_dsn=rabbitmq_url))
    await broker.connect()
    try:
        await broker.declare_exchange(EMBEDDING_JOBS)

        with pytest.raises(Exception, match="NO_ROUTE"):
            await _publish(broker)
    finally:
        await broker.stop()


async def test_publish_with_bound_queue_succeeds(rabbitmq_url: str) -> None:
    """Появилась очередь — та же публикация проходит."""
    broker = build_broker(Settings(rabbitmq_dsn=rabbitmq_url))
    await broker.connect()
    try:
        exchange = await broker.declare_exchange(
            RabbitExchange(
                EMBEDDING_JOBS.name, type=ExchangeType.TOPIC, durable=True
            )
        )
        queue = await broker.declare_queue(_QUEUE)
        await queue.bind(exchange, routing_key=_ROUTING_KEY)

        await _publish(broker)
    finally:
        await broker.stop()
