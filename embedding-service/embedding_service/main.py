"""Точка входа: обе транспортные плоскости на одном event loop (D2, D7).

Runtime-обвязка (вне coverage): грузит модель один раз, прогревает, открывает
readiness, поднимает gRPC-сервер + FastStream-консюмер + ops, дренирует на
остановке.
"""

import asyncio
import logging

from embedding_service.application.exceptions import ProbeFailed
from embedding_service.bootstrap import Deps, build_deps
from embedding_service.infrastructure.config import get_settings
from embedding_service.infrastructure.observability.logging import (
    configure_logging,
)
from embedding_service.infrastructure.reranker_config import (
    get_reranker_settings,
)
from embedding_service.presentation.grpc.health import (
    build_health_servicer,
    set_serving,
)
from embedding_service.presentation.grpc.reranker_servicer import (
    RerankerServicer,
)
from embedding_service.presentation.grpc.server import build_server
from embedding_service.presentation.grpc.servicer import EmbeddingServicer
from embedding_service.presentation.messaging.consumer_app import (
    build_consumer,
)

_RERANKER_SERVICE = "reranker.v1.RerankerService"
_logger = logging.getLogger(__name__)


async def run() -> None:  # pragma: no cover - runtime (запуск серверов)
    """Собирает и запускает сервис до сигнала остановки."""
    configure_logging()
    settings = get_settings()
    deps = build_deps(settings, get_reranker_settings())

    ready = {"value": False}
    try:
        await deps.warmup.handle()  # загрузка+прогрев модели (§8)
    except ProbeFailed:
        await deps.aclose()
        raise
    ready["value"] = True

    health = build_health_servicer()
    await set_serving(health, serving=True)

    # Reranker — изолированный жизненный цикл: сбой его прогрева НЕ роняет
    # embeddings (graceful degrade → NOT_SERVING / Rerank отвечает UNAVAILABLE).
    reranker_ready = {"value": False}
    reranker_servicer = await _prepare_reranker(deps, health, reranker_ready)

    servicer = EmbeddingServicer(deps.embed_query, deps.embed_queries)
    server, _ = build_server(
        servicer,
        health,
        reranker_servicer=reranker_servicer,
        address=f"{settings.grpc_host}:{settings.grpc_port}",
        reflection_enabled=True,
    )
    app = build_consumer(
        deps,
        lambda: ready["value"],
        reranker_ready=(
            (lambda: reranker_ready["value"])
            if deps.reranker_configured
            else None
        ),
    )

    await server.start()
    try:
        # блокирует: uvicorn (ops+/metrics) + broker lifespan.
        await app.run(
            run_extra_options={
                "host": settings.ops_host,
                "port": settings.ops_http_port,
            }
        )
    finally:
        ready["value"] = False
        reranker_ready["value"] = False
        await set_serving(health, serving=False)
        if deps.reranker_configured:
            await set_serving(health, serving=False, service=_RERANKER_SERVICE)
        await server.stop(grace=settings.graceful_timeout)
        await deps.aclose()


async def _prepare_reranker(
    deps: Deps,
    health: object,
    reranker_ready: dict[str, bool],
) -> RerankerServicer | None:
    """Готовит reranker изолированно; его сбой не влияет на embeddings.

    Выключен → ``None``: RerankerService не регистрируется и Rerank отвечает
    UNIMPLEMENTED. Включён → servicer возвращается всегда, даже если провайдер
    не создался или прогрев упал: тогда готовности нет, health отдаёт
    NOT_SERVING, а Rerank — UNAVAILABLE.
    """
    if not deps.reranker_configured:
        return None
    servicer = RerankerServicer(
        deps.rerank_documents, lambda: reranker_ready["value"]
    )
    if deps.reranker_provider is None:
        # Провайдер не создался в composition root — уже залогировано там.
        _logger.warning("reranker-провайдер не создан, Rerank недоступен")
    else:
        try:
            await deps.reranker_provider.warmup()
            reranker_ready["value"] = True
        except Exception as exc:  # любой сбой прогрева reranker — не фатален
            _logger.warning("reranker недоступен, продолжаем без него: %s", exc)
    await set_serving(
        health, serving=reranker_ready["value"], service=_RERANKER_SERVICE
    )
    return servicer


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
