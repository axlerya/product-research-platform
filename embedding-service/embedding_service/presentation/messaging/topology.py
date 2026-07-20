"""Топология RabbitMQ: main + retry-ladder + parking (§5.4, D14).

Приватные exchange (retry/requeue/parking) держат ретрай-трафик внутри
embedding-service и не задевают других потребителей ``embedding.jobs``.
"""

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

REQUESTED_RK = "embedding.documents.requested.v1"
GENERATED_RK = "embedding.documents.generated.v1"

MAIN_QUEUE_NAME = "embedding.documents.requests"
RETRY_QUEUE_NAME = "embedding.documents.requests.retry"
PARKING_QUEUE_NAME = "embedding.documents.requests.dlq"

JOBS_EXCHANGE = RabbitExchange(
    "embedding.jobs", type=ExchangeType.TOPIC, durable=True
)
EVENTS_EXCHANGE = RabbitExchange(
    "embedding.events", type=ExchangeType.TOPIC, durable=True
)
RETRY_EXCHANGE = RabbitExchange(
    "embedding.retry", type=ExchangeType.TOPIC, durable=True
)
REQUEUE_EXCHANGE = RabbitExchange(
    "embedding.requeue", type=ExchangeType.TOPIC, durable=True
)
PARKING_EXCHANGE = RabbitExchange(
    "embedding.parking", type=ExchangeType.TOPIC, durable=True
)


def main_queue() -> RabbitQueue:
    """Основная очередь (quorum): reject → retry-exchange (backoff)."""
    return RabbitQueue(
        MAIN_QUEUE_NAME,
        durable=True,
        routing_key=REQUESTED_RK,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": RETRY_EXCHANGE.name,
        },
    )


def retry_queue(ttl_ms: int) -> RabbitQueue:
    """Retry-очередь: держит TTL, затем dead-letter в requeue-exchange."""
    return RabbitQueue(
        RETRY_QUEUE_NAME,
        durable=True,
        routing_key=REQUESTED_RK,
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
        routing_key=REQUESTED_RK,
    )
