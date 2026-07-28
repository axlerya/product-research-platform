"""FastStream consumer-app: команды документов + ops (§5.5, D2).

Один процесс потребляет команды и отдаёт ops-плоскость (/health,/ready,
/metrics). gRPC-сервер запросов живёт в том же процессе (composition root).
Проводка — вне coverage; логика в error_policy/serialization покрыта unit.
"""

import json
from collections.abc import Callable

from faststream import AckPolicy
from faststream.asgi import AsgiFastStream, make_ping_asgi
from faststream.rabbit import Channel, RabbitBroker, RabbitMessage
from prometheus_client import make_asgi_app

from embedding_service.application.dto import DocumentsGenerated
from embedding_service.bootstrap import Deps
from embedding_service.presentation.api.ops import readiness_asgi
from embedding_service.presentation.messaging.error_policy import dispatch
from embedding_service.presentation.messaging.schemas import RequestedEnvelope
from embedding_service.presentation.messaging.serialization import (
    to_generated_envelope,
)
from embedding_service.presentation.messaging.topology import (
    EVENTS_EXCHANGE,
    GENERATED_RK,
    JOBS_EXCHANGE,
    PARKING_EXCHANGE,
    REQUESTED_RK,
    REQUEUE_EXCHANGE,
    RETRY_EXCHANGE,
    main_queue,
    parking_queue,
    retry_queue,
)


def build_broker(deps: Deps) -> RabbitBroker:
    """Брокер: publish дожидается confirm брокера (aio-pika confirm-канал)."""
    return RabbitBroker(
        deps.settings.rabbitmq_dsn,
        graceful_timeout=deps.settings.graceful_timeout,
        # QoS был объявлен в настройках, но никуда не доходил.
        default_channel=Channel(prefetch_count=deps.settings.prefetch_count),
    )


def build_consumer(
    deps: Deps,
    is_ready: Callable[[], bool],
    reranker_ready: Callable[[], bool] | None = None,
) -> AsgiFastStream:
    """Собирает AsgiFastStream: subscriber команд + ops-маршруты.

    ``reranker_ready`` (при включённом reranker) добавляет отдельный пробник
    ``/reranker/ready`` — readiness reranker независим от embeddings ``/ready``.
    """
    broker = build_broker(deps)
    # mandatory=True — брокер вернёт несматченное сообщение (basic.return).
    generated = broker.publisher(
        exchange=EVENTS_EXCHANGE, routing_key=GENERATED_RK, mandatory=True
    )

    async def _publish(
        envelope: RequestedEnvelope, result: DocumentsGenerated
    ) -> None:
        wire = to_generated_envelope(
            envelope,
            result,
            event_id=deps.id_generator.new_uuid7(),
            occurred_at=deps.clock.now(),
        )
        headers = {"message_id": wire["event_id"]}
        if envelope.trace_id is not None:
            headers["trace_id"] = envelope.trace_id
        await generated.publish(wire, headers=headers)

    async def _park(message: RabbitMessage) -> None:
        await broker.publish(
            message.body,
            exchange=PARKING_EXCHANGE,
            routing_key=REQUESTED_RK,
            headers=dict(message.headers),
        )

    queue = main_queue()

    # Подписчик ровно один: второй декоратор нужен был только ради привязки
    # очереди к requeue-exchange, но попутно создавал второго консюмера на той
    # же очереди. Привязка объявляется декларативно при старте.
    @broker.subscriber(queue, JOBS_EXCHANGE, ack_policy=AckPolicy.MANUAL)
    async def on_requested(msg: RabbitMessage) -> None:
        payload = json.loads(msg.body)
        await dispatch(
            payload,
            msg,
            use_case=deps.embed_documents,
            publish=_publish,
            park=_park,
            max_attempts=deps.settings.max_attempts,
        )

    routes = [
        ("/health", make_ping_asgi(broker, timeout=5.0)),
        ("/ready", readiness_asgi(is_ready)),
        ("/metrics", make_asgi_app(deps.registry)),
    ]
    if reranker_ready is not None:
        routes.append(("/reranker/ready", readiness_asgi(reranker_ready)))

    app = AsgiFastStream(broker, asgi_routes=routes)

    @app.after_startup
    async def _declare_topology() -> None:
        """Объявляет лестницу main → retry(TTL) → requeue → parking.

        Без неё основная очередь ссылается на несуществующий dead-letter
        exchange, и брокер молча выбрасывает каждое отклонённое сообщение:
        ни ретраев, ни DLQ — команда на эмбеддинг просто исчезает.
        """
        retry_ex = await broker.declare_exchange(RETRY_EXCHANGE)
        requeue_ex = await broker.declare_exchange(REQUEUE_EXCHANGE)
        parking_ex = await broker.declare_exchange(PARKING_EXCHANGE)
        main_q = await broker.declare_queue(queue)
        retry_q = await broker.declare_queue(
            retry_queue(deps.settings.retry_ttl_ms)
        )
        parking_q = await broker.declare_queue(parking_queue())
        # Возврат из retry-лестницы приходит в ту же основную очередь.
        await main_q.bind(requeue_ex, routing_key=REQUESTED_RK)
        await retry_q.bind(retry_ex, routing_key=REQUESTED_RK)
        await parking_q.bind(parking_ex, routing_key=REQUESTED_RK)

    return app
