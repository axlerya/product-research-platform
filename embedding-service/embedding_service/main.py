"""Точка входа: обе транспортные плоскости на одном event loop (D2, D7).

Runtime-обвязка (вне coverage): грузит модель один раз, прогревает, открывает
readiness, поднимает gRPC-сервер + FastStream-консюмер + ops, дренирует на
остановке.
"""

import asyncio

from embedding_service.application.exceptions import ProbeFailed
from embedding_service.bootstrap import build_deps
from embedding_service.infrastructure.config import get_settings
from embedding_service.infrastructure.observability.logging import (
    configure_logging,
)
from embedding_service.presentation.grpc.health import (
    build_health_servicer,
    set_serving,
)
from embedding_service.presentation.grpc.server import build_server
from embedding_service.presentation.grpc.servicer import EmbeddingServicer
from embedding_service.presentation.messaging.consumer_app import (
    build_consumer,
)


async def run() -> None:  # pragma: no cover - runtime (запуск серверов)
    """Собирает и запускает сервис до сигнала остановки."""
    configure_logging()
    settings = get_settings()
    deps = build_deps(settings)

    ready = {"value": False}
    try:
        await deps.warmup.handle()  # загрузка+прогрев модели (§8)
    except ProbeFailed:
        await deps.aclose()
        raise
    ready["value"] = True

    health = build_health_servicer()
    await set_serving(health, serving=True)
    servicer = EmbeddingServicer(deps.embed_query, deps.embed_queries)
    server, _ = build_server(
        servicer,
        health,
        address=f"{settings.grpc_host}:{settings.grpc_port}",
        reflection_enabled=True,
    )
    app = build_consumer(deps, lambda: ready["value"])

    await server.start()
    try:
        await app.run()  # блокирует: uvicorn (ops+/metrics) + broker lifespan
    finally:
        ready["value"] = False
        await set_serving(health, serving=False)
        await server.stop(grace=settings.graceful_timeout)
        await deps.aclose()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
