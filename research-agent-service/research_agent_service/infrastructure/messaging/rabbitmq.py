"""RabbitMQ-адаптер: брокер, durable topic-обмен, публикация конвертов.

`RabbitEventPublisher` реализует порт EventPublisher: публикует JSON-конверт
события в topic-обмен по routing_key (== event_type) с publisher confirms.
Используется только relay'ем — write-path в брокер не пишет.
"""

from collections.abc import Mapping

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange

_EXCHANGE_NAME = "research-agent.events"


def build_broker(dsn: str) -> RabbitBroker:
    """Брокер RabbitMQ (publisher confirms для надёжной публикации)."""
    return RabbitBroker(dsn)


def build_exchange() -> RabbitExchange:
    """Durable topic-обмен доменных событий."""
    return RabbitExchange(_EXCHANGE_NAME, type=ExchangeType.TOPIC, durable=True)


class RabbitEventPublisher:
    """Публикация конверта события в topic-обмен (порт EventPublisher)."""

    def __init__(
        self, *, broker: RabbitBroker, exchange: RabbitExchange
    ) -> None:
        self._broker = broker
        self._exchange = exchange

    async def publish(
        self,
        payload: Mapping[str, object],
        *,
        routing_key: str,
        message_id: str,
        headers: Mapping[str, str],
    ) -> None:
        """Публикует JSON-конверт по routing_key (ожидает confirm)."""
        await self._broker.publish(
            dict(payload),
            exchange=self._exchange,
            routing_key=routing_key,
            message_id=message_id,
            headers=dict(headers),
        )
