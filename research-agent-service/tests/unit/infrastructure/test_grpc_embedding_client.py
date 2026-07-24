"""Тесты GrpcEmbeddingClient на фейковом стабе."""

from research_agent_service.infrastructure.grpc._generated import embedding_pb2
from research_agent_service.infrastructure.grpc.embedding_client import (
    GrpcEmbeddingClient,
)


class _FakeStub:
    """Стаб, возвращающий заранее заданный ответ; ловит timeout."""

    def __init__(self, response: embedding_pb2.EmbedQueryResponse) -> None:
        self._response = response
        self.timeout: float | None = None

    async def EmbedQuery(
        self, request: embedding_pb2.EmbedQueryRequest, **kwargs: float
    ) -> embedding_pb2.EmbedQueryResponse:
        self.timeout = kwargs.get("timeout")
        return self._response


async def test_embed_query_maps_response_and_passes_deadline() -> None:
    """Ответ разбирается в QueryEmbedding; дедлайн передаётся в вызов."""
    response = embedding_pb2.EmbedQueryResponse(
        embedding=embedding_pb2.QueryEmbedding(
            dense=embedding_pb2.DenseVector(values=[0.5, 0.25]),
            sparse=embedding_pb2.SparseVector(indices=[3], values=[0.5]),
            token_count=7,
        ),
        model_version="bge-m3",
        dim=1024,
    )
    stub = _FakeStub(response)
    client = GrpcEmbeddingClient(stub=stub, deadline_s=2.0)

    result = await client.embed_query("наушники")

    assert result.dense == (0.5, 0.25)
    assert result.sparse_indices == (3,)
    assert result.sparse_values == (0.5,)
    assert result.model_version == "bge-m3"
    assert result.token_count == 7
    assert stub.timeout == 2.0
