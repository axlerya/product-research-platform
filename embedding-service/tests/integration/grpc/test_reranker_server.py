"""Integration: grpc.aio in-process reranker — реальный сервер + клиент.

FAKE-провайдер (deterministic, без torch): команда → RerankerServicer →
ранжирование → ответ. Проверяются порядок, top_n, deadline и readiness.
"""

import grpc
import pytest

from embedding_service.application.use_cases.rerank_documents import (
    RerankDocuments,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2_grpc as rpc,
)
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.infrastructure.reranking.factory import (
    build_reranker_provider,
)
from embedding_service.presentation.grpc.reranker_servicer import (
    RerankerServicer,
)

pytestmark = pytest.mark.integration


def _servicer(*, is_ready: bool = True) -> RerankerServicer:
    settings = RerankerSettings(
        _env_file=None, provider_mode="deterministic", max_documents=10
    )
    use_case = RerankDocuments(
        build_reranker_provider(settings), settings.limits()
    )
    return RerankerServicer(use_case, lambda: is_ready, deadline_guard_s=1.0)


def _docs(*ids: str) -> list[pb.RerankDocument]:
    return [pb.RerankDocument(id=i, text=f"текст-{i}") for i in ids]


async def _serve(servicer: RerankerServicer):
    server = grpc.aio.server()
    rpc.add_RerankerServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    return server, port


async def test_rerank_end_to_end() -> None:
    server, port = await _serve(_servicer())
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = rpc.RerankerServiceStub(channel)

            response = await stub.Rerank(
                pb.RerankRequest(
                    query="куртка",
                    documents=_docs("a", "b", "c"),
                    return_documents=True,
                ),
                timeout=5,
            )
            assert len(response.results) == 3
            scores = [r.score for r in response.results]
            assert scores == sorted(scores, reverse=True)
            assert response.model_version.endswith("|norm=1")
            # return_documents=True → текст эхо-транслирован.
            assert all(r.text.startswith("текст-") for r in response.results)

            top = await stub.Rerank(
                pb.RerankRequest(
                    query="куртка", documents=_docs("a", "b", "c"), top_n=2
                ),
                timeout=5,
            )
            assert len(top.results) == 2
    finally:
        await server.stop(grace=None)


async def test_rerank_deadline_exceeded() -> None:
    server, port = await _serve(_servicer())
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = rpc.RerankerServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as info:
                await stub.Rerank(
                    pb.RerankRequest(query="q", documents=_docs("a")),
                    timeout=0.5,
                )
            assert info.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED
    finally:
        await server.stop(grace=None)


async def test_rerank_unavailable_when_not_ready() -> None:
    server, port = await _serve(_servicer(is_ready=False))
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = rpc.RerankerServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as info:
                await stub.Rerank(
                    pb.RerankRequest(query="q", documents=_docs("a")),
                    timeout=5,
                )
            assert info.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await server.stop(grace=None)
