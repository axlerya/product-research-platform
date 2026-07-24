"""Интеграционный roundtrip публикации в RabbitMQ (контейнер)."""

import asyncio
import json

import pytest
from faststream.rabbit import RabbitQueue

from research_agent_service.infrastructure.messaging.rabbitmq import (
    RabbitEventPublisher,
    build_broker,
    build_exchange,
)

pytestmark = pytest.mark.integration

_ROUTING_KEY = "agent.query.completed.v1"


async def _get_message(queue: object) -> object:
    """Ждёт одно сообщение из очереди (basic.get с ограниченным опросом)."""
    for _ in range(50):
        message = await queue.get(fail=False)
        if message is not None:
            return message
        await asyncio.sleep(0.1)
    raise AssertionError("сообщение не пришло в очередь")


async def test_publish_roundtrip(rabbitmq_url: str) -> None:
    """Опубликованный конверт доходит до связанной очереди с метаданными."""
    broker = build_broker(rabbitmq_url)
    exchange = build_exchange()
    await broker.connect()
    try:
        declared_exchange = await broker.declare_exchange(exchange)
        queue = await broker.declare_queue(
            RabbitQueue("test-roundtrip", durable=False, auto_delete=True)
        )
        await queue.bind(declared_exchange, routing_key=_ROUTING_KEY)

        publisher = RabbitEventPublisher(broker=broker, exchange=exchange)
        await publisher.publish(
            {"event_type": _ROUTING_KEY, "data": {"answer": "ok"}},
            routing_key=_ROUTING_KEY,
            message_id="msg-42",
            headers={"trace_id": "trace-1"},
        )

        message = await _get_message(queue)
        assert json.loads(message.body) == {
            "event_type": _ROUTING_KEY,
            "data": {"answer": "ok"},
        }
        assert message.message_id == "msg-42"
        assert message.headers["trace_id"] == "trace-1"
        await message.ack()
    finally:
        await broker.stop()
