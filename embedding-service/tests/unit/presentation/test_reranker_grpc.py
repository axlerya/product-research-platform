"""Unit-тесты gRPC reranker: mappers + servicer (fake context)."""

import grpc
import pytest

from embedding_service.application.use_cases.rerank_documents import (
    RerankDocuments,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as pb,
)
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.infrastructure.reranking.factory import (
    build_reranker_provider,
)
from embedding_service.presentation.grpc.reranker_mappers import (
    to_rerank_command,
)
from embedding_service.presentation.grpc.reranker_servicer import (
    RerankerServicer,
)


def _request(
    *docs: tuple[str, str],
    query: str = "куртка",
    top_n: int | None = None,
    return_documents: bool = False,
) -> pb.RerankRequest:
    request = pb.RerankRequest(
        query=query,
        documents=[pb.RerankDocument(id=i, text=t) for i, t in docs],
        return_documents=return_documents,
    )
    if top_n is not None:
        request.top_n = top_n
    return request


class TestMappers:
    def test_command_maps_documents_and_top_n(self) -> None:
        command = to_rerank_command(_request(("a", "t1"), ("b", "t2"), top_n=1))
        assert command.query == "куртка"
        assert [d.text_id for d in command.documents] == ["a", "b"]
        assert command.top_n == 1

    def test_command_top_n_absent_is_none(self) -> None:
        assert to_rerank_command(_request(("a", "t1"))).top_n is None


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


def _servicer(
    *, is_ready: bool = True, deadline_guard_s: float = 0.005
) -> RerankerServicer:
    settings = RerankerSettings(
        _env_file=None, provider_mode="deterministic", max_documents=10
    )
    use_case = RerankDocuments(
        build_reranker_provider(settings), settings.limits()
    )
    return RerankerServicer(
        use_case, lambda: is_ready, deadline_guard_s=deadline_guard_s
    )


class TestRerankerServicer:
    async def test_rerank_happy_orders_by_score(self) -> None:
        response = await _servicer().Rerank(
            _request(("a", "t1"), ("b", "t2"), ("c", "t3")), _FakeContext()
        )
        assert len(response.results) == 3
        scores = [r.score for r in response.results]
        assert scores == sorted(scores, reverse=True)
        assert response.model_version.endswith("|norm=1")

    async def test_rerank_applies_top_n(self) -> None:
        response = await _servicer().Rerank(
            _request(("a", "t1"), ("b", "t2"), ("c", "t3"), top_n=2),
            _FakeContext(),
        )
        assert len(response.results) == 2

    async def test_return_documents_echoes_text(self) -> None:
        response = await _servicer().Rerank(
            _request(("a", "alpha"), ("b", "beta"), return_documents=True),
            _FakeContext(),
        )
        by_id = {r.id: r.text for r in response.results}
        assert by_id == {"a": "alpha", "b": "beta"}

    async def test_no_return_documents_leaves_text_empty(self) -> None:
        response = await _servicer().Rerank(
            _request(("a", "alpha")), _FakeContext()
        )
        assert response.results[0].text == ""

    async def test_not_ready_aborts_unavailable(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer(is_ready=False).Rerank(
                _request(("a", "t1")), _FakeContext()
            )
        assert info.value.code == grpc.StatusCode.UNAVAILABLE

    async def test_deadline_aborts(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().Rerank(
                _request(("a", "t1")), _FakeContext(time_remaining=0.001)
            )
        assert info.value.code == grpc.StatusCode.DEADLINE_EXCEEDED

    async def test_empty_query_aborts_invalid(self) -> None:
        with pytest.raises(_Abort) as info:
            await _servicer().Rerank(
                _request(("a", "t1"), query="   "), _FakeContext()
            )
        assert info.value.code == grpc.StatusCode.INVALID_ARGUMENT
