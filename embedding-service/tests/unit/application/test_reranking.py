"""Unit-тесты application-слоя reranking: RerankDocuments + порт.

Провайдер подменяется фейком (без модели/torch). Проверяется маппинг
доменных ошибок в прикладные (fail-fast → ValidationError; дефект инференса
→ InferenceError), порядок/скор и отсечение top_n.
"""

from collections.abc import Sequence

import pytest

from embedding_service.application.dto.reranking import (
    RerankDocumentsCommand,
    RerankInputDocument,
)
from embedding_service.application.exceptions import (
    InferenceError,
    ValidationError,
)
from embedding_service.application.ports.reranker_provider import (
    RerankerProvider,
)
from embedding_service.application.use_cases.rerank_documents import (
    RerankDocuments,
)
from embedding_service.domain.value_objects.reranking.limits import (
    RerankLimits,
)
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)

_MODEL_ID = RerankerModelId(
    name="BAAI/bge-reranker-v2-m3", revision="unknown", normalized=True
)


class _FakeReranker:
    """Фейковый провайдер: возвращает заранее заданные скоры по порядку."""

    def __init__(self, scores: Sequence[float]) -> None:
        self._scores = list(scores)
        self.seen: tuple[str, tuple[str, ...]] | None = None

    @property
    def model_id(self) -> RerankerModelId:
        return _MODEL_ID

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        self.seen = (query, tuple(documents))
        return list(self._scores)

    async def warmup(self) -> None:  # pragma: no cover - не вызывается в U
        ...

    async def probe(self):  # pragma: no cover - не вызывается в U
        raise NotImplementedError


def _limits() -> RerankLimits:
    return RerankLimits(
        max_documents=5,
        max_query_chars=100,
        max_document_chars=100,
        max_total_bytes=100_000,
    )


def _command(
    *docs: tuple[str, str], query: str = "куртка", top_n: int | None = None
) -> RerankDocumentsCommand:
    return RerankDocumentsCommand(
        query=query,
        documents=tuple(RerankInputDocument(i, t) for i, t in docs),
        top_n=top_n,
    )


def test_port_is_protocol() -> None:
    # Фейк структурно соответствует порту.
    provider: RerankerProvider = _FakeReranker([0.1])
    assert provider.model_id.key.endswith("|norm=1")


class TestRerankDocuments:
    async def test_ranks_by_score_descending(self) -> None:
        provider = _FakeReranker([0.2, 0.9, 0.5])
        use_case = RerankDocuments(provider, _limits())
        result = await use_case.handle(
            _command(("a", "t1"), ("b", "t2"), ("c", "t3"))
        )
        assert [i.text_id.value for i in result.items] == ["b", "c", "a"]
        assert result.model_id.key == _MODEL_ID.key

    async def test_preserves_original_index(self) -> None:
        provider = _FakeReranker([0.2, 0.9, 0.5])
        use_case = RerankDocuments(provider, _limits())
        result = await use_case.handle(
            _command(("a", "t1"), ("b", "t2"), ("c", "t3"))
        )
        # index — исходная позиция во входе, не позиция после сортировки.
        assert [i.index for i in result.items] == [1, 2, 0]

    async def test_top_n_truncates(self) -> None:
        provider = _FakeReranker([0.2, 0.9, 0.5])
        use_case = RerankDocuments(provider, _limits())
        result = await use_case.handle(
            _command(("a", "t1"), ("b", "t2"), ("c", "t3"), top_n=2)
        )
        assert [i.text_id.value for i in result.items] == ["b", "c"]

    async def test_provider_receives_query_and_docs(self) -> None:
        provider = _FakeReranker([0.5, 0.5])
        use_case = RerankDocuments(provider, _limits())
        await use_case.handle(
            _command(("a", "d1"), ("b", "d2"), query="запрос")
        )
        assert provider.seen == ("запрос", ("d1", "d2"))

    async def test_empty_query_is_validation_error(self) -> None:
        use_case = RerankDocuments(_FakeReranker([0.5]), _limits())
        with pytest.raises(ValidationError):
            await use_case.handle(_command(("a", "t1"), query="   "))

    async def test_empty_documents_is_validation_error(self) -> None:
        use_case = RerankDocuments(_FakeReranker([]), _limits())
        with pytest.raises(ValidationError):
            await use_case.handle(_command())

    async def test_too_many_documents_is_validation_error(self) -> None:
        limits = RerankLimits(
            max_documents=1,
            max_query_chars=100,
            max_document_chars=100,
            max_total_bytes=100_000,
        )
        use_case = RerankDocuments(_FakeReranker([0.1, 0.2]), limits)
        with pytest.raises(ValidationError):
            await use_case.handle(_command(("a", "t1"), ("b", "t2")))

    async def test_invalid_top_n_is_validation_error(self) -> None:
        # top_n=0 — клиентская ошибка, а не транзиент инференса.
        use_case = RerankDocuments(_FakeReranker([0.1]), _limits())
        with pytest.raises(ValidationError):
            await use_case.handle(_command(("a", "t1"), top_n=0))

    async def test_score_count_mismatch_is_inference_error(self) -> None:
        provider = _FakeReranker([0.1])  # 1 скор на 2 документа
        use_case = RerankDocuments(provider, _limits())
        with pytest.raises(InferenceError):
            await use_case.handle(_command(("a", "t1"), ("b", "t2")))

    async def test_non_finite_score_is_inference_error(self) -> None:
        provider = _FakeReranker([float("nan")])
        use_case = RerankDocuments(provider, _limits())
        with pytest.raises(InferenceError):
            await use_case.handle(_command(("a", "t1")))
