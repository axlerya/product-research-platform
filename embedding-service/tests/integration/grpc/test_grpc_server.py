"""Integration: grpc.aio in-process — реальный сервер + клиент (§11.4)."""

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from embedding_service.application.use_cases.embed_queries import EmbedQueries
from embedding_service.application.use_cases.embed_query import EmbedQuery
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingProvider,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2_grpc as rpc,
)
from embedding_service.presentation.grpc.health import (
    build_health_servicer,
    set_serving,
)
from embedding_service.presentation.grpc.server import build_server
from embedding_service.presentation.grpc.servicer import EmbeddingServicer

pytestmark = pytest.mark.integration


def _mid(dim: int = 8) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


async def test_grpc_server_end_to_end() -> None:
    provider = DeterministicEmbeddingProvider(model_id=_mid(8))
    limits = EmbeddingLimits(
        max_texts=5, max_text_chars=50, max_tokens=8192, max_total_bytes=10_000
    )
    servicer = EmbeddingServicer(
        EmbedQuery(provider, limits),
        EmbedQueries(provider, limits),
        deadline_guard_s=1.0,
    )
    health_srv = build_health_servicer()
    await set_serving(health_srv, serving=True)
    server, port = build_server(
        servicer,
        health_srv,
        address="127.0.0.1:0",
        reflection_enabled=True,
    )
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = rpc.EmbeddingServiceStub(channel)

            response = await stub.EmbedQuery(
                pb.EmbedQueryRequest(text="hello"), timeout=5
            )
            assert response.dim == 8
            assert len(response.embedding.dense.values) == 8
            assert response.model_version == _mid(8).key

            batch = await stub.EmbedQueries(
                pb.EmbedQueriesRequest(texts=["a", "bb"]), timeout=5
            )
            assert len(batch.embeddings) == 2

            with pytest.raises(grpc.aio.AioRpcError) as deadline:
                await stub.EmbedQuery(
                    pb.EmbedQueryRequest(text="hi"), timeout=0.5
                )
            assert deadline.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED

            with pytest.raises(grpc.aio.AioRpcError) as invalid:
                await stub.EmbedQuery(
                    pb.EmbedQueryRequest(text="  "), timeout=5
                )
            assert invalid.value.code() == grpc.StatusCode.INVALID_ARGUMENT

            health_stub = health_pb2_grpc.HealthStub(channel)
            report = await health_stub.Check(
                health_pb2.HealthCheckRequest(service="")
            )
            assert report.status == health_pb2.HealthCheckResponse.SERVING
    finally:
        await server.stop(grace=None)
