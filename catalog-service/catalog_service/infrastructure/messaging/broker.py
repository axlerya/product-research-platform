"""Брокер RabbitMQ и publisher событий (FastStream).

Топология: topic-exchange ``catalog.events``; routing key = ``event_type``.
Publisher — отдельный процесс-relay (не HTTP-хендлер).
"""

from typing import Any, Protocol

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange

from catalog_service.infrastructure.config import Settings

CATALOG_EVENTS = RabbitExchange(
    "catalog.events", type=ExchangeType.TOPIC, durable=True
)


class EventPublisher(Protocol):
    """Абстракция публикации события в брокер (для тестируемости relay)."""

    async def publish(
        self,
        payload: dict[str, Any],
        *,
        routing_key: str,
        message_id: str,
        headers: dict[str, str],
    ) -> None:
        """Публикует событие с заданным routing key и message-id."""
        ...


def build_broker(settings: Settings) -> RabbitBroker:
    """Создаёт брокер RabbitMQ (подключение — при старте FastStream)."""
    return RabbitBroker(settings.rabbitmq_dsn)


class RabbitEventPublisher:
    """Publisher поверх ``RabbitBroker`` в topic-exchange ``catalog.events``."""

    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish(
        self,
        payload: dict[str, Any],
        *,
        routing_key: str,
        message_id: str,
        headers: dict[str, str],
    ) -> None:
        await self._broker.publish(
            payload,
            exchange=CATALOG_EVENTS,
            routing_key=routing_key,
            message_id=message_id,
            headers=headers,
        )
