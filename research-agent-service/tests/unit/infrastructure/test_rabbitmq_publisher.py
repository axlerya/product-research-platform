"""Тесты RabbitEventPublisher на фейковом брокере."""

from collections.abc import Mapping

from faststream.rabbit import RabbitBroker, RabbitExchange

from research_agent_service.infrastructure.messaging.rabbitmq import (
    RabbitEventPublisher,
    build_broker,
    build_exchange,
)


class _FakeBroker:
    """Записывает аргументы publish вместо реальной отправки."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    async def publish(
        self, message: Mapping[str, object], **kwargs: object
    ) -> None:
        self.calls.append((message, kwargs))


def test_build_broker_returns_broker() -> None:
    """build_broker строит RabbitBroker без подключения."""
    assert isinstance(
        build_broker("amqp://guest:guest@localhost/"), RabbitBroker
    )


def test_build_exchange_is_durable_topic() -> None:
    """Обмен — durable topic."""
    exchange = build_exchange()
    assert isinstance(exchange, RabbitExchange)
    assert exchange.durable is True


async def test_publish_forwards_envelope() -> None:
    """publish пробрасывает payload/routing_key/message_id/headers/exchange."""
    broker = _FakeBroker()
    exchange = build_exchange()
    publisher = RabbitEventPublisher(broker=broker, exchange=exchange)

    await publisher.publish(
        {"event_type": "agent.query.completed.v1"},
        routing_key="agent.query.completed.v1",
        message_id="msg-1",
        headers={"trace_id": "t-1"},
    )

    (message, kwargs) = broker.calls[0]
    assert message == {"event_type": "agent.query.completed.v1"}
    assert kwargs["routing_key"] == "agent.query.completed.v1"
    assert kwargs["message_id"] == "msg-1"
    assert kwargs["headers"] == {"trace_id": "t-1"}
    assert kwargs["exchange"] is exchange
