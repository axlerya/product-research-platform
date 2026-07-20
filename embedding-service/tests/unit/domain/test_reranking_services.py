"""Unit-тесты доменных сервисов reranking: TopNSelector, RerankValidator."""

import pytest

from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    EmptyBatchError,
    RequestTooLargeError,
    TextTooLongError,
)
from embedding_service.domain.services.reranking.top_n_selector import (
    TopNSelector,
)
from embedding_service.domain.services.reranking.validator import (
    RerankValidator,
)
from embedding_service.domain.value_objects.reranking.candidate import (
    RerankCandidate,
)
from embedding_service.domain.value_objects.reranking.limits import (
    RerankLimits,
)
from embedding_service.domain.value_objects.reranking.query import RerankQuery
from embedding_service.domain.value_objects.reranking.ranked_item import (
    RankedItem,
)
from embedding_service.domain.value_objects.reranking.relevance_score import (
    RelevanceScore,
)
from embedding_service.domain.value_objects.reranking.top_n import TopN
from embedding_service.domain.value_objects.text_id import TextId


def _item(text_id: str, index: int, score: float) -> RankedItem:
    return RankedItem(TextId(text_id), index, RelevanceScore(score))


class TestTopNSelector:
    def test_sorts_by_score_descending(self) -> None:
        items = [
            _item("a", 0, 0.2),
            _item("b", 1, 0.9),
            _item("c", 2, 0.5),
        ]
        ordered = TopNSelector.select(items, None)
        assert [i.text_id.value for i in ordered] == ["b", "c", "a"]

    def test_ties_broken_by_original_index(self) -> None:
        items = [
            _item("a", 0, 0.5),
            _item("b", 1, 0.5),
            _item("c", 2, 0.5),
        ]
        ordered = TopNSelector.select(items, None)
        # Равные скоры сохраняют исходный порядок (детерминированно).
        assert [i.text_id.value for i in ordered] == ["a", "b", "c"]

    def test_top_n_truncates(self) -> None:
        items = [
            _item("a", 0, 0.2),
            _item("b", 1, 0.9),
            _item("c", 2, 0.5),
        ]
        ordered = TopNSelector.select(items, TopN(2))
        assert [i.text_id.value for i in ordered] == ["b", "c"]

    def test_top_n_larger_than_list_returns_all(self) -> None:
        items = [_item("a", 0, 0.2), _item("b", 1, 0.9)]
        ordered = TopNSelector.select(items, TopN(10))
        assert len(ordered) == 2

    def test_empty_returns_empty(self) -> None:
        assert TopNSelector.select([], None) == ()


class TestRerankValidator:
    def _limits(self) -> RerankLimits:
        return RerankLimits(
            max_documents=3,
            max_query_chars=20,
            max_document_chars=20,
            max_total_bytes=10_000,
        )

    def _candidates(self, n: int) -> list[RerankCandidate]:
        return [RerankCandidate(TextId(f"d{i}"), "текст") for i in range(n)]

    def test_valid_passes(self) -> None:
        RerankValidator.validate(
            RerankQuery("куртка"), self._candidates(3), self._limits()
        )

    def test_empty_documents_rejected(self) -> None:
        with pytest.raises(EmptyBatchError):
            RerankValidator.validate(RerankQuery("куртка"), [], self._limits())

    def test_too_many_documents_rejected(self) -> None:
        with pytest.raises(BatchTooLargeError):
            RerankValidator.validate(
                RerankQuery("куртка"), self._candidates(4), self._limits()
            )

    def test_query_too_long_rejected(self) -> None:
        with pytest.raises(TextTooLongError):
            RerankValidator.validate(
                RerankQuery("q" * 21), self._candidates(1), self._limits()
            )

    def test_document_too_long_rejected(self) -> None:
        candidates = [RerankCandidate(TextId("d0"), "x" * 21)]
        with pytest.raises(TextTooLongError):
            RerankValidator.validate(
                RerankQuery("куртка"), candidates, self._limits()
            )

    def test_total_bytes_exceeded_rejected(self) -> None:
        limits = RerankLimits(
            max_documents=3,
            max_query_chars=100,
            max_document_chars=100,
            max_total_bytes=8,
        )
        with pytest.raises(RequestTooLargeError):
            RerankValidator.validate(
                RerankQuery("query"),
                [RerankCandidate(TextId("d0"), "document")],
                limits,
            )
