"""Unit-тесты ``DeterministicRerankerProvider`` — FAKE для CI/smoke."""

from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)
from embedding_service.infrastructure.reranking.deterministic import (
    DeterministicRerankerProvider,
)


def _provider() -> DeterministicRerankerProvider:
    model_id = RerankerModelId(
        name="BAAI/bge-reranker-v2-m3", revision="unknown", normalized=True
    )
    return DeterministicRerankerProvider(model_id=model_id)


class TestDeterministicReranker:
    async def test_scores_aligned_to_documents(self) -> None:
        scores = await _provider().rerank("q", ["d1", "d2", "d3"])
        assert len(scores) == 3

    async def test_scores_in_unit_interval(self) -> None:
        scores = await _provider().rerank("q", ["d1", "d2"])
        assert all(0.0 <= s < 1.0 for s in scores)

    async def test_deterministic(self) -> None:
        a = await _provider().rerank("куртка", ["товар a", "товар b"])
        b = await _provider().rerank("куртка", ["товар a", "товар b"])
        assert a == b

    async def test_distinct_docs_distinct_scores(self) -> None:
        scores = await _provider().rerank("q", ["alpha", "omega"])
        assert scores[0] != scores[1]

    async def test_depends_on_query(self) -> None:
        s1 = await _provider().rerank("q1", ["doc"])
        s2 = await _provider().rerank("q2", ["doc"])
        assert s1 != s2

    async def test_model_id(self) -> None:
        assert _provider().model_id.key.endswith("|norm=1")

    async def test_probe(self) -> None:
        status = await _provider().probe()
        assert status.loaded is True
        assert status.precision == "fake"
        assert status.model_key.startswith("BAAI/bge-reranker-v2-m3")

    async def test_warmup_and_aclose_noop(self) -> None:
        provider = _provider()
        assert await provider.warmup() is None
        assert await provider.aclose() is None
