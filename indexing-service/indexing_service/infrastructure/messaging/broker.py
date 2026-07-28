"""Брокер RabbitMQ и publisher команд на эмбеддинг (FastStream).

Топология исходящего плеча: topic-exchange ``embedding.jobs``; routing key =
``event_type`` (``embedding.documents.requested.v1``). Публикует отдельный
процесс-relay поверх outbox — не хендлер консюмера.
"""

from typing import Any, Protocol

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange
from pamqp.commands import Basic

from indexing_service.infrastructure.config import Settings

EMBEDDING_JOBS = RabbitExchange(
    "embedding.jobs", type=ExchangeType.TOPIC, durable=True
)


class UnroutableMessage(RuntimeError):
    """Брокер вернул команду: подходящей очереди для ключа нет."""


def ensure_routed(confirmation: Any, *, routing_key: str) -> None:
    """Превращает возврат сообщения брокером в ошибку публикации.

    ``publish`` с mandatory не бросает сам: он отдаёт подтверждение, внутри
    которого лежит ``Basic.Return``. Без этой проверки relay пометил бы
    невостребованную команду опубликованной, а задание на эмбеддинг зависло
    бы до сверки (например, если embedding-service ещё не объявил очередь).
    """
    if isinstance(getattr(confirmation, "delivery", None), Basic.Return):
        raise UnroutableMessage(
            f"Брокер вернул сообщение: нет очереди для {routing_key!r}"
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
    """Создаёт брокер RabbitMQ (подключение — при старте FastStream)."""
    return RabbitBroker(settings.rabbitmq_dsn)


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
        confirmation = await self._broker.publish(
            payload,
            exchange=EMBEDDING_JOBS,
            routing_key=routing_key,
            message_id=message_id,
            headers=headers,
        )
        ensure_routed(confirmation, routing_key=routing_key)
