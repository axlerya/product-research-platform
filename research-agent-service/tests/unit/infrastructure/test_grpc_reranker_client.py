"""Тесты GrpcRerankerClient на фейковом стабе."""

from decimal import Decimal

import grpc
import pytest
from grpc.aio import AioRpcError, Metadata

from research_agent_service.application.dto.retrieval import RerankDocument
from research_agent_service.application.exceptions import RerankerUnavailable
from research_agent_service.infrastructure.grpc._generated import reranker_pb2
from research_agent_service.infrastructure.grpc.reranker_client import (
    GrpcRerankerClient,
)


class _FakeStub:
    """Возвращает ответ или бросает заданную gRPC-ошибку."""

    def __init__(
        self,
        *,
        response: reranker_pb2.RerankResponse | None = None,
        error: AioRpcError | None = None,
    ) -> None:
        self._response = response
        self._error = error

    async def Rerank(
        self, request: reranker_pb2.RerankRequest, **kwargs: float
    ) -> reranker_pb2.RerankResponse:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _error(code: grpc.StatusCode) -> AioRpcError:
    return AioRpcError(code, Metadata(), Metadata(), details="x")


async def test_rerank_maps_results() -> None:
    """Успех: RankedDocument → RankedDoc с Decimal-скором."""
    response = reranker_pb2.RerankResponse(
        results=[
            reranker_pb2.RankedDocument(id="SKU-2", index=1, score=0.95),
            reranker_pb2.RankedDocument(id="SKU-1", index=0, score=0.80),
        ],
        model_version="bge-reranker",
    )
    client = GrpcRerankerClient(stub=_FakeStub(response=response))

    result = await client.rerank(
        "наушники", (RerankDocument(id="SKU-1", text="t"),), top_n=2
    )

    assert [d.id for d in result] == ["SKU-2", "SKU-1"]
    assert result[0].score == Decimal("0.95")


async def test_unavailable_code_raises_reranker_unavailable() -> None:
    """UNIMPLEMENTED (reranker выключен) → RerankerUnavailable."""
    stub = _FakeStub(error=_error(grpc.StatusCode.UNIMPLEMENTED))
    client = GrpcRerankerClient(stub=stub)

    with pytest.raises(RerankerUnavailable):
        await client.rerank("q", (RerankDocument(id="x", text="t"),), top_n=1)


async def test_other_code_is_reraised() -> None:
    """Иные коды (например INTERNAL) не глушатся деградацией."""
    stub = _FakeStub(error=_error(grpc.StatusCode.INTERNAL))
    client = GrpcRerankerClient(stub=stub)

    with pytest.raises(AioRpcError):
        await client.rerank("q", (RerankDocument(id="x", text="t"),), top_n=1)
