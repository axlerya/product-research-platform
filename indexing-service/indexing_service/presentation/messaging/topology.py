"""Топология RabbitMQ консюмера: main + retry-ladder + parking (§7.3).

Приватные exchange (retry/requeue/parking) держат ретрай-трафик внутри
indexing-service и не задевают других потребителей ``catalog.events``.
"""

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

_ROUTING = "catalog.product.*"

CATALOG_EXCHANGE = RabbitExchange(
    "catalog.events", type=ExchangeType.TOPIC, durable=True
)
RETRY_EXCHANGE = RabbitExchange(
    "indexing.retry", type=ExchangeType.TOPIC, durable=True
)
REQUEUE_EXCHANGE = RabbitExchange(
    "indexing.requeue", type=ExchangeType.TOPIC, durable=True
)
PARKING_EXCHANGE = RabbitExchange(
    "indexing.parking", type=ExchangeType.TOPIC, durable=True
)

MAIN_QUEUE_NAME = "indexing.catalog.products"
PARKING_QUEUE_NAME = "indexing.catalog.products.dlq"


def main_queue() -> RabbitQueue:
    """Основная очередь: reject → retry-exchange (backoff-лестница).

    ``x-single-active-consumer`` — часть корректности, а не тюнинг. Обработка
    события это read-modify-write водяного знака точки, и параллельный разбор
    двух событий одного товара приводит к тому, что более старое применяется
    последним и затирает новое. Внутри процесса это удерживает замок по
    товару, а между репликами — брокер: сообщения получает только один
    консюмер, остальные ждут и подхватывают при его падении.
    """
    return RabbitQueue(
        MAIN_QUEUE_NAME,
        durable=True,
        routing_key=_ROUTING,
        arguments={
            "x-dead-letter-exchange": RETRY_EXCHANGE.name,
            "x-single-active-consumer": True,
        },
    )


def retry_queue(ttl_ms: int) -> RabbitQueue:
    """Retry-очередь: держит TTL, затем dead-letter в requeue-exchange."""
    return RabbitQueue(
        "indexing.catalog.products.retry",
        durable=True,
        routing_key=_ROUTING,
        arguments={
            "x-message-ttl": ttl_ms,
            "x-dead-letter-exchange": REQUEUE_EXCHANGE.name,
        },
    )


def parking_queue() -> RabbitQueue:
    """Терминальная очередь (parking) для ручного разбора / replay."""
    return RabbitQueue(
        PARKING_QUEUE_NAME,
        durable=True,
        routing_key=_ROUTING,
    )
