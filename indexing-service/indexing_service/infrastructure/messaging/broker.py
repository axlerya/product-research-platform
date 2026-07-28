"""Брокер RabbitMQ и publisher команд на эмбеддинг (FastStream).

Топология исходящего плеча: topic-exchange ``embedding.jobs``; routing key =
``event_type`` (``embedding.documents.requested.v1``). Публикует отдельный
процесс-relay поверх outbox — не хендлер консюмера.
"""

from typing import Any, Protocol

from faststream.rabbit import (
    Channel,
    ExchangeType,
    RabbitBroker,
    RabbitExchange,
)

from indexing_service.infrastructure.config import Settings

EMBEDDING_JOBS = RabbitExchange(
    "embedding.jobs", type=ExchangeType.TOPIC, durable=True
)


class EventPublisher(Protocol):
    """Абстракция публикации команды в брокер (для тестируемости relay)."""

    async def publish(
        self,
        payload: dict[str, Any],
        *,
        routing_key: str,
        message_id: str,
        headers: dict[str, str],
    ) -> None:
        """Публикует команду с заданным routing key и message-id."""
        ...


def build_broker(settings: Settings) -> RabbitBroker:
    """Создаёт брокер RabbitMQ (подключение — при старте FastStream).

    ``on_return_raises`` обязателен для relay: сам по себе publish возврат
    сообщения брокером не считает ошибкой и отдаёт подтверждение с
    ``Basic.Return`` внутри. Без этого outbox пометил бы невостребованную
    команду опубликованной — например, когда embedding-service ещё не
    объявил свою очередь, — и задание зависло бы до сверки.
    """
    return RabbitBroker(
        settings.rabbitmq_dsn,
        default_channel=Channel(on_return_raises=True),
    )


class RabbitEmbeddingPublisher:
    """Publisher поверх ``RabbitBroker`` в exchange ``embedding.jobs``."""

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
            exchange=EMBEDDING_JOBS,
            routing_key=routing_key,
            message_id=message_id,
            headers=headers,
        )
