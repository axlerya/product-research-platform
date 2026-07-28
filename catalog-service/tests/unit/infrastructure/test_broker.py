"""Тесты publisher событий через ``TestRabbitBroker`` (без RabbitMQ)."""

import pytest
from faststream.rabbit import RabbitQueue, TestRabbitBroker
from pamqp.commands import Basic

from catalog_service.infrastructure.config import Settings
from catalog_service.infrastructure.messaging.broker import (
    CATALOG_EVENTS,
    RabbitEventPublisher,
    UnroutableMessage,
    build_broker,
)


class _StubBroker:
    """Брокер, возвращающий заданное подтверждение публикации."""

    def __init__(self, confirmation: object) -> None:
        self._confirmation = confirmation

    async def publish(self, *args: object, **kwargs: object) -> object:
        return self._confirmation


class _Confirmation:
    """Ответ брокера на публикацию (``delivery`` — Ack либо Return)."""

    def __init__(self, delivery: object) -> None:
        self.delivery = delivery


async def _publish(confirmation: object) -> None:
    await RabbitEventPublisher(_StubBroker(confirmation)).publish(
        {"event_type": "catalog.product.created"},
        routing_key="catalog.product.created",
        message_id="m1",
        headers={},
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


async def test_returned_message_is_reported_as_failure():
    """Возврат брокером = недоставка: relay обязан повторить, а не забыть.

    Publish с mandatory сам не бросает — он отдаёт подтверждение с
    ``Basic.Return`` внутри. Без явной проверки outbox пометил бы такое
    событие опубликованным, и оно потерялось бы молча.
    """
    with pytest.raises(UnroutableMessage) as failure:
        await _publish(_Confirmation(Basic.Return()))

    assert "catalog.product.created" in str(failure.value)


async def test_acked_message_is_reported_as_success():
    """Обычное подтверждение публикации ошибкой не считается."""
    await _publish(_Confirmation(Basic.Ack()))


async def test_missing_confirmation_is_reported_as_success():
    """Отсутствие подтверждения (канал без confirms) не ломает публикацию."""
    await _publish(None)
