"""Performance-тесты reranker.

FAKE-замер (детерминированный провайдер) — быстрый, проверяет пропускную
способность ранжирования; реальная модель — под ``slow``/``nightly``
(исключены из основного прогона, требуют весов).
"""

import time

import pytest

from embedding_service.application.dto.reranking import (
    RerankDocumentsCommand,
    RerankInputDocument,
)
from embedding_service.application.use_cases.rerank_documents import (
    RerankDocuments,
)
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.infrastructure.reranking.factory import (
    build_reranker_provider,
)

pytestmark = pytest.mark.performance


def _use_case() -> RerankDocuments:
    settings = RerankerSettings(
        _env_file=None,
        provider_mode="deterministic",
        max_batch_size=64,
        max_documents=1000,
        max_query_chars=1000,
        max_document_chars=1000,
        max_total_bytes=10_000_000,
    )
    provider = build_reranker_provider(settings)
    return RerankDocuments(provider, settings.limits())


async def test_fake_reranker_ranks_500_docs_fast() -> None:
    use_case = _use_case()
    documents = tuple(
        RerankInputDocument(f"d{i}", f"документ номер {i} про товары")
        for i in range(500)
    )
    command = RerankDocumentsCommand(
        query="зимняя куртка", documents=documents, top_n=10
    )
    start = time.perf_counter()
    result = await use_case.handle(command)
    elapsed = time.perf_counter() - start
    assert result.size == 10
    # FAKE-ранжирование 500 документов — заметно быстрее секунды.
    assert elapsed < 3.0


@pytest.mark.slow
@pytest.mark.nightly
async def test_real_reranker_latency_budget() -> None:
    pytest.importorskip("FlagEmbedding")
    settings = RerankerSettings(
        _env_file=None,
        provider_mode="bge_reranker",
        device="cpu",
        precision="fp32",
    )
    provider = build_reranker_provider(settings)
    try:
        await provider.warmup()
        documents = [f"кандидат {i}" for i in range(20)]
        start = time.perf_counter()
        scores = await provider.rerank("запрос", documents)
        elapsed = time.perf_counter() - start
        assert len(scores) == 20
        assert elapsed < 30.0  # щедрый бюджет CPU-инференса 20 пар
    finally:
        await provider.aclose()
