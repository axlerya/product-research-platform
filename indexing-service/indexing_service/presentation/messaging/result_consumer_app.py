"""FastStream consumer-app: embedding.events → ApplyEmbeddingResult (§6, §10).

Отдельный процесс от консюмера каталога и от relay. Потребляет
``embedding.documents.generated.v1``, отдаёт ``/health`` и ``/metrics``.
Запуск: ``uvicorn
indexing_service.presentation.messaging.result_consumer_app:app``.
"""

from typing import Any

from faststream import AckPolicy, Context, ContextRepo
from faststream.asgi import AsgiFastStream, make_ping_asgi
from faststream.rabbit import RabbitBroker, RabbitMessage
from faststream.rabbit.prometheus import RabbitPrometheusMiddleware
from prometheus_client import CollectorRegistry, make_asgi_app

from indexing_service.bootstrap import build_result_consumer
from indexing_service.infrastructure.config import get_settings
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)
from indexing_service.presentation.messaging.embedding_topology import (
    EMBEDDING_EVENTS,
    RESULT_PARKING_EXCHANGE,
    RESULT_REQUEUE_EXCHANGE,
    RESULT_RETRY_EXCHANGE,
    ROUTING_KEY,
    result_main_queue,
    result_parking_queue,
    result_retry_queue,
)
from indexing_service.presentation.messaging.result_dispatch import (
    dispatch_result,
)

_settings = get_settings()
_registry = CollectorRegistry()
broker = RabbitBroker(
    _settings.rabbitmq_dsn,
    graceful_timeout=30,
    middlewares=[RabbitPrometheusMiddleware(registry=_registry)],
)
app = AsgiFastStream(
    broker,
    asgi_routes=[
        ("/health", make_ping_asgi(broker, timeout=5.0)),
        ("/metrics", make_asgi_app(_registry)),
    ],
)
_MAIN = result_main_queue()


async def _park(message: RabbitMessage) -> None:
    """Публикует сообщение в parking-exchange (терминальный DLQ)."""
    await broker.publish(
        message.body,
        exchange=RESULT_PARKING_EXCHANGE,
        routing_key=message.raw_message.routing_key,
        headers=dict(message.headers),
        persist=True,
    )


@broker.subscriber(_MAIN, EMBEDDING_EVENTS, ack_policy=AckPolicy.MANUAL)
@broker.subscriber(_MAIN, RESULT_REQUEUE_EXCHANGE, ack_policy=AckPolicy.MANUAL)
async def on_embedding_result(
    envelope: EmbeddingEventEnvelope,
    message: RabbitMessage,
    use_case: Any = Context("use_case"),
    parker: Any = Context("parker"),
    max_attempts: int = Context("max_attempts"),
) -> None:
    await dispatch_result(
        envelope,
        message,
        use_case=use_case,
        park=parker,
        max_attempts=max_attempts,
    )


@app.on_startup
async def _startup(context: ContextRepo) -> None:
    deps = build_result_consumer(_settings)
    context.set_global("deps", deps)
    context.set_global("use_case", deps.use_case)
    context.set_global("parker", _park)
    context.set_global("max_attempts", _settings.max_attempts)


@app.after_startup
async def _declare_topology(context: ContextRepo) -> None:
    retry_ex = await broker.declare_exchange(RESULT_RETRY_EXCHANGE)
    parking_ex = await broker.declare_exchange(RESULT_PARKING_EXCHANGE)
    retry_q = await broker.declare_queue(
        result_retry_queue(_settings.retry_ttl_ms)
    )
    parking_q = await broker.declare_queue(result_parking_queue())
    await retry_q.bind(retry_ex, routing_key=ROUTING_KEY)
    await parking_q.bind(parking_ex, routing_key=ROUTING_KEY)


@app.on_shutdown
async def _shutdown(context: ContextRepo) -> None:
    deps = context.get("deps")
    if deps is not None:
        await deps.aclose()
