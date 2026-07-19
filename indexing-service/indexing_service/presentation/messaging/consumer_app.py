"""FastStream consumer-app: подписка catalog.events + retry/DLQ (§3, §7).

Запуск: ``faststream run
indexing_service.presentation.messaging.consumer_app:app``.
"""

from typing import Any

from faststream import AckPolicy, Context, ContextRepo, FastStream
from faststream.rabbit import RabbitBroker, RabbitMessage

from indexing_service.bootstrap import build_consumer
from indexing_service.infrastructure.config import get_settings
from indexing_service.presentation.messaging.error_policy import dispatch
from indexing_service.presentation.messaging.schemas import CatalogEnvelope
from indexing_service.presentation.messaging.topology import (
    CATALOG_EXCHANGE,
    PARKING_EXCHANGE,
    REQUEUE_EXCHANGE,
    RETRY_EXCHANGE,
    main_queue,
    parking_queue,
    retry_queue,
)

_settings = get_settings()
broker = RabbitBroker(_settings.rabbitmq_dsn, graceful_timeout=30)
app = FastStream(broker)
_MAIN = main_queue()


async def _park(message: RabbitMessage) -> None:
    """Публикует сообщение в parking-exchange (терминальный DLQ)."""
    await broker.publish(
        message.body,
        exchange=PARKING_EXCHANGE,
        routing_key=message.raw_message.routing_key,
        headers=dict(message.headers),
        persist=True,
    )


@broker.subscriber(_MAIN, CATALOG_EXCHANGE, ack_policy=AckPolicy.MANUAL)
@broker.subscriber(_MAIN, REQUEUE_EXCHANGE, ack_policy=AckPolicy.MANUAL)
async def on_catalog_event(
    envelope: CatalogEnvelope,
    message: RabbitMessage,
    use_case: Any = Context("use_case"),
    parker: Any = Context("parker"),
    max_attempts: int = Context("max_attempts"),
) -> None:
    await dispatch(
        envelope,
        message,
        use_case=use_case,
        park=parker,
        max_attempts=max_attempts,
    )


@app.on_startup
async def _startup(context: ContextRepo) -> None:
    deps = await build_consumer(_settings)
    context.set_global("deps", deps)
    context.set_global("use_case", deps.use_case)
    context.set_global("parker", _park)
    context.set_global("max_attempts", _settings.max_attempts)


@app.after_startup
async def _declare_topology(context: ContextRepo) -> None:
    retry_ex = await broker.declare_exchange(RETRY_EXCHANGE)
    parking_ex = await broker.declare_exchange(PARKING_EXCHANGE)
    retry_q = await broker.declare_queue(retry_queue(_settings.retry_ttl_ms))
    parking_q = await broker.declare_queue(parking_queue())
    await retry_q.bind(retry_ex, routing_key="catalog.product.*")
    await parking_q.bind(parking_ex, routing_key="catalog.product.*")


@app.on_shutdown
async def _shutdown(context: ContextRepo) -> None:
    deps = context.get("deps")
    if deps is not None:
        await deps.aclose()
