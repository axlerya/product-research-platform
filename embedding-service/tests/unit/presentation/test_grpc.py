"""Unit-тесты gRPC: status_map, mappers, servicer (fake context), health."""

import grpc
import pytest

from embedding_service.application.exceptions import (
    InferenceError,
    InferenceOverloadedError,
    InferenceTimeoutError,
    ModelNotReadyError,
    ProbeFailed,
    ValidationError,
)
from embedding_service.application.use_cases.embed_queries import EmbedQueries
from embedding_service.application.use_cases.embed_query import EmbedQuery
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.sparse_vector import SparseVector
from embedding_service.domain.value_objects.token_count import TokenCount
from embedding_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingProvider,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as pb,
)
from embedding_service.presentation.grpc.health import (
    build_health_servicer,
    set_serving,
)
from embedding_service.presentation.grpc.mappers import to_query_embedding
from embedding_service.presentation.grpc.servicer import EmbeddingServicer
from embedding_service.presentation.grpc.status_map import to_status_code


def _mid(dim: int = 8) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


class TestStatusMap:
    @pytest.mark.parametrize(
        ("exc", "code"),
        [
            (ValidationError("x"), grpc.StatusCode.INVALID_ARGUMENT),
            (ProbeFailed("x"), grpc.StatusCode.FAILED_PRECONDITION),
            (
                InferenceOverloadedError(queue_depth=1),
                grpc.StatusCode.RESOURCE_EXHAUSTED,
            ),
            (InferenceTimeoutError(), grpc.StatusCode.DEADLINE_EXCEEDED),
            (ModelNotReadyError("x"), grpc.StatusCode.UNAVAILABLE),
            (InferenceError("x"), grpc.StatusCode.INTERNAL),
        ],
    )
    def test_mapping(self, exc: Exception, code: grpc.StatusCode) -> None:
        assert to_status_code(exc) == code

    def test_unknown_defaults_internal(self) -> None:
        assert to_status_code(RuntimeError("x")) == grpc.StatusCode.INTERNAL


def test_to_query_embedding() -> None:
    emb = Embedding(
        DenseVector((0.1, 0.2)), SparseVector((3, 7), (0.5, 0.9)), _mid(2)
    )
    proto = to_query_embedding(emb, TokenCount(11))
    assert list(proto.dense.values) == pytest.approx([0.1, 0.2])
    assert list(proto.sparse.indices) == [3, 7]
    assert proto.token_count == 11


class _Abort(Exception):
    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        self.code = code
        self.details = details


class _FakeContext:
    def __init__(self, time_remaining: float | None = None) -> None:
        self._time_remaining = time_remaining

    def time_remaining(self) -> float | None:
        return self._time_remaining

    async def abort(self, code: grpc.StatusCode, details: str) -> None:
        raise _Abort(code, details)


def _servicer() -> EmbeddingServicer:
    provider = DeterministicEmbeddingProvider(model_id=_mid(8))
    limits = EmbeddingLimits(
        max_texts=5, max_text_chars=50, max_tokens=8192, max_total_bytes=10_000
    )
    return EmbeddingServicer(
        EmbedQuery(provider, limits), EmbedQueries(provider, limits)
    )


class TestServicer:
    async def test_embed_query_happy(self) -> None:
        response = await _servicer().EmbedQuery(
            pb.EmbedQueryRequest(text="hello", request_id="r"), _FakeContext()
        )
        assert response.dim == 8
        assert response.model_version == _mid(8).key
        assert len(response.embedding.dense.values) == 8

    async def test_embed_query_empty_text(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().EmbedQuery(
                pb.EmbedQueryRequest(text="   "), _FakeContext()
            )
        assert info.value.code == grpc.StatusCode.INVALID_ARGUMENT

    async def test_embed_query_deadline(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().EmbedQuery(
                pb.EmbedQueryRequest(text="hi"),
                _FakeContext(time_remaining=0.001),
            )
        assert info.value.code == grpc.StatusCode.DEADLINE_EXCEEDED

    async def test_embed_query_too_long_maps_invalid(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().EmbedQuery(
                pb.EmbedQueryRequest(text="x" * 51), _FakeContext()
            )
        assert info.value.code == grpc.StatusCode.INVALID_ARGUMENT

    async def test_embed_queries_happy_order(self) -> None:
        response = await _servicer().EmbedQueries(
            pb.EmbedQueriesRequest(texts=["a", "bb", "ccc"]), _FakeContext()
        )
        assert len(response.embeddings) == 3
        assert response.dim == 8

    async def test_embed_queries_empty_batch_invalid(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().EmbedQueries(
                pb.EmbedQueriesRequest(texts=[]), _FakeContext()
            )
        assert info.value.code == grpc.StatusCode.INVALID_ARGUMENT

    async def test_embed_queries_deadline(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().EmbedQueries(
                pb.EmbedQueriesRequest(texts=["a"]),
                _FakeContext(time_remaining=0.0),
            )
        assert info.value.code == grpc.StatusCode.DEADLINE_EXCEEDED


async def test_health_build_and_toggle() -> None:
    servicer = build_health_servicer()
    await set_serving(servicer, serving=True)
    await set_serving(
        servicer, serving=False, service="embedding.v1.EmbeddingService"
    )
