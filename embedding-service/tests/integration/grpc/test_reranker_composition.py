"""Integration: composition reranker on/off + graceful degrade (grpc.aio).

Проверяет проводку build_deps + build_server: включённый reranker обслуживает
обе плоскости; выключенный → RerankerService отсутствует (UNIMPLEMENTED),
embeddings не затронуты; неготовый reranker → UNAVAILABLE, embeddings живут;
сбой создания провайдера → health NOT_SERVING + UNAVAILABLE, embeddings живут.
"""

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from embedding_service import bootstrap
from embedding_service.bootstrap import build_deps
from embedding_service.infrastructure.config import Settings
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as epb,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2_grpc as erpc,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as rpb,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2_grpc as rrpc,
)
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.main import _prepare_reranker
from embedding_service.presentation.grpc.health import (
    build_health_servicer,
    set_serving,
)
from embedding_service.presentation.grpc.reranker_servicer import (
    RerankerServicer,
)
from embedding_service.presentation.grpc.server import build_server
from embedding_service.presentation.grpc.servicer import EmbeddingServicer

pytestmark = pytest.mark.integration


async def _build(*, reranker_enabled: bool, reranker_ready: bool = True):
    settings = Settings(_env_file=None, provider_mode="deterministic", dim=8)
    reranker_settings = RerankerSettings(
        _env_file=None,
        enabled=reranker_enabled,
        provider_mode="deterministic",
        max_documents=10,
    )
    deps = build_deps(settings, reranker_settings)
    health = build_health_servicer()
    await set_serving(health, serving=True)
    reranker_servicer = None
    if deps.reranker_enabled:
        reranker_servicer = RerankerServicer(
            deps.rerank_documents,
            lambda: reranker_ready,
            deadline_guard_s=1.0,
        )
    server, port = build_server(
        EmbeddingServicer(
            deps.embed_query, deps.embed_queries, deadline_guard_s=1.0
        ),
        health,
        reranker_servicer=reranker_servicer,
        address="127.0.0.1:0",
        reflection_enabled=True,
    )
    await server.start()
    return deps, server, port


def _rerank_request() -> rpb.RerankRequest:
    return rpb.RerankRequest(
        query="куртка",
        documents=[
            rpb.RerankDocument(id="a", text="t1"),
            rpb.RerankDocument(id="b", text="t2"),
        ],
        top_n=1,
    )


async def test_enabled_serves_both_planes() -> None:
    deps, server, port = await _build(reranker_enabled=True)
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            emb = await erpc.EmbeddingServiceStub(channel).EmbedQuery(
                epb.EmbedQueryRequest(text="hello"), timeout=5
            )
            assert emb.dim == 8
            rr = await rrpc.RerankerServiceStub(channel).Rerank(
                _rerank_request(), timeout=5
            )
            assert len(rr.results) == 1
    finally:
        await server.stop(grace=None)
        await deps.aclose()


async def test_disabled_is_unimplemented_embeddings_unaffected() -> None:
    deps, server, port = await _build(reranker_enabled=False)
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            emb = await erpc.EmbeddingServiceStub(channel).EmbedQuery(
                epb.EmbedQueryRequest(text="hello"), timeout=5
            )
            assert emb.dim == 8
            with pytest.raises(grpc.aio.AioRpcError) as info:
                await rrpc.RerankerServiceStub(channel).Rerank(
                    _rerank_request(), timeout=5
                )
            assert info.value.code() == grpc.StatusCode.UNIMPLEMENTED
    finally:
        await server.stop(grace=None)
        await deps.aclose()


async def _build_with_failed_reranker(monkeypatch):
    """Reranker включён, но его провайдер не создался (сбой загрузки)."""

    def _boom(settings: RerankerSettings) -> None:
        raise RuntimeError("не найдены веса BAAI/bge-reranker-v2-m3")

    monkeypatch.setattr(bootstrap, "build_reranker_provider", _boom)
    settings = Settings(_env_file=None, provider_mode="deterministic", dim=8)
    reranker_settings = RerankerSettings(
        _env_file=None,
        enabled=True,
        provider_mode="deterministic",
        max_documents=10,
    )
    deps = build_deps(settings, reranker_settings)
    health = build_health_servicer()
    await set_serving(health, serving=True)
    # Реальная проводка graceful degrade из composition root.
    reranker_servicer = await _prepare_reranker(deps, health, {"value": False})
    server, port = build_server(
        EmbeddingServicer(
            deps.embed_query, deps.embed_queries, deadline_guard_s=1.0
        ),
        health,
        reranker_servicer=reranker_servicer,
        address="127.0.0.1:0",
        reflection_enabled=True,
    )
    await server.start()
    return deps, server, port


async def test_build_failure_degrades_gracefully(monkeypatch) -> None:
    deps, server, port = await _build_with_failed_reranker(monkeypatch)
    try:
        assert deps.reranker_configured is True
        assert deps.reranker_enabled is False
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            # Embeddings продолжают работать несмотря на сбой reranker.
            emb = await erpc.EmbeddingServiceStub(channel).EmbedQuery(
                epb.EmbedQueryRequest(text="hello"), timeout=5
            )
            assert emb.dim == 8
            # Health reranker — NOT_SERVING.
            checked = await health_pb2_grpc.HealthStub(channel).Check(
                health_pb2.HealthCheckRequest(
                    service="reranker.v1.RerankerService"
                ),
                timeout=5,
            )
            assert checked.status == health_pb2.HealthCheckResponse.NOT_SERVING
            # Rerank — UNAVAILABLE, а не UNIMPLEMENTED.
            with pytest.raises(grpc.aio.AioRpcError) as info:
                await rrpc.RerankerServiceStub(channel).Rerank(
                    _rerank_request(), timeout=5
                )
            assert info.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await server.stop(grace=None)
        await deps.aclose()


async def test_not_ready_degrades_gracefully() -> None:
    # Включён, но reranker не готов (симуляция провала прогрева).
    deps, server, port = await _build(
        reranker_enabled=True, reranker_ready=False
    )
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            # Embeddings работают несмотря на неготовый reranker.
            emb = await erpc.EmbeddingServiceStub(channel).EmbedQuery(
                epb.EmbedQueryRequest(text="hello"), timeout=5
            )
            assert emb.dim == 8
            with pytest.raises(grpc.aio.AioRpcError) as info:
                await rrpc.RerankerServiceStub(channel).Rerank(
                    _rerank_request(), timeout=5
                )
            assert info.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await server.stop(grace=None)
        await deps.aclose()
