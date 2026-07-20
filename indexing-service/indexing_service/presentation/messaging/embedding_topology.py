"""Топология консюмера результатов эмбеддинга (§7, §10).

Отдельная приватная лестница ``main→retry(TTL)→requeue→parking`` под своими
именами: ретрай-трафик результатов не задевает ни консюмер каталога, ни
других потребителей ``embedding.events``.
"""

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

ROUTING_KEY = "embedding.documents.generated.v1"

EMBEDDING_EVENTS = RabbitExchange(
    "embedding.events", type=ExchangeType.TOPIC, durable=True
)
RESULT_RETRY_EXCHANGE = RabbitExchange(
    "indexing.embeddings.retry", type=ExchangeType.TOPIC, durable=True
)
RESULT_REQUEUE_EXCHANGE = RabbitExchange(
    "indexing.embeddings.requeue", type=ExchangeType.TOPIC, durable=True
)
RESULT_PARKING_EXCHANGE = RabbitExchange(
    "indexing.embeddings.parking", type=ExchangeType.TOPIC, durable=True
)

RESULT_MAIN_QUEUE_NAME = "indexing.embeddings.generated"
RESULT_PARKING_QUEUE_NAME = "indexing.embeddings.generated.dlq"


def result_main_queue() -> RabbitQueue:
    """Основная очередь: reject → retry-exchange (backoff-лестница)."""
    return RabbitQueue(
        RESULT_MAIN_QUEUE_NAME,
        durable=True,
        routing_key=ROUTING_KEY,
        arguments={"x-dead-letter-exchange": RESULT_RETRY_EXCHANGE.name},
    )


def result_retry_queue(ttl_ms: int) -> RabbitQueue:
    """Retry-очередь: держит TTL, затем dead-letter в requeue-exchange."""
    return RabbitQueue(
        "indexing.embeddings.generated.retry",
        durable=True,
        routing_key=ROUTING_KEY,
        arguments={
            "x-message-ttl": ttl_ms,
            "x-dead-letter-exchange": RESULT_REQUEUE_EXCHANGE.name,
        },
    )


def result_parking_queue() -> RabbitQueue:
    """Терминальная очередь (parking) для ручного разбора / replay."""
    return RabbitQueue(
        RESULT_PARKING_QUEUE_NAME,
        durable=True,
        routing_key=ROUTING_KEY,
    )
