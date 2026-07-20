"""Unit-тесты доменных VO reranking: изолированный подпакет.

RerankerModelId, RelevanceScore, RankedItem, TopN, RerankLimits,
RerankQuery, RerankCandidate, RerankResult. Инварианты — как у embedding-VO:
частные проверки в ``__post_init__`` с доменными исключениями.
"""

import math

import pytest

from embedding_service.domain.exceptions import (
    EmptyTextError,
    InvalidLimitsError,
    InvalidModelIdError,
)
from embedding_service.domain.value_objects.reranking.candidate import (
    RerankCandidate,
)
from embedding_service.domain.value_objects.reranking.exceptions import (
    InvalidRankedItemError,
    InvalidScoreError,
    InvalidTopNError,
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
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)
from embedding_service.domain.value_objects.reranking.result import (
    RerankResult,
)
from embedding_service.domain.value_objects.reranking.top_n import TopN
from embedding_service.domain.value_objects.text_id import TextId


class TestRerankerModelId:
    def test_key_is_canonical_watermark(self) -> None:
        model_id = RerankerModelId(
            name="BAAI/bge-reranker-v2-m3",
            revision="unknown",
            normalized=True,
        )
        assert model_id.key == "BAAI/bge-reranker-v2-m3@unknown|norm=1"

    def test_key_reflects_normalized_flag(self) -> None:
        model_id = RerankerModelId(name="m", revision="r", normalized=False)
        assert model_id.key == "m@r|norm=0"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(InvalidModelIdError):
            RerankerModelId(name="  ", revision="r", normalized=True)


class TestRelevanceScore:
    def test_holds_finite_value(self) -> None:
        assert RelevanceScore(0.73).value == pytest.approx(0.73)

    def test_negative_logit_allowed(self) -> None:
        # Ненормированный скор reranker — это логит, может быть отрицательным.
        assert RelevanceScore(-4.2).value == pytest.approx(-4.2)

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite_rejected(self, bad: float) -> None:
        with pytest.raises(InvalidScoreError):
            RelevanceScore(bad)


class TestTopN:
    def test_holds_positive(self) -> None:
        assert TopN(5).value == 5

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_rejected(self, bad: int) -> None:
        with pytest.raises(InvalidTopNError):
            TopN(bad)


class TestRankedItem:
    def test_holds_id_index_score(self) -> None:
        item = RankedItem(TextId("d1"), 0, RelevanceScore(0.9))
        assert item.text_id.value == "d1"
        assert item.index == 0
        assert item.score.value == pytest.approx(0.9)

    def test_negative_index_rejected(self) -> None:
        with pytest.raises(InvalidRankedItemError):
            RankedItem(TextId("d1"), -1, RelevanceScore(0.9))


class TestRerankQuery:
    def test_holds_value_and_char_length(self) -> None:
        query = RerankQuery("красная куртка")
        assert query.value == "красная куртка"
        assert query.char_length == len("красная куртка")

    def test_empty_rejected(self) -> None:
        with pytest.raises(EmptyTextError):
            RerankQuery("   ")


class TestRerankCandidate:
    def test_holds_id_and_text(self) -> None:
        cand = RerankCandidate(TextId("p1"), "куртка зимняя")
        assert cand.text_id.value == "p1"
        assert cand.text == "куртка зимняя"
        assert cand.char_length == len("куртка зимняя")

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(EmptyTextError):
            RerankCandidate(TextId("p1"), "  ")


class TestRerankLimits:
    def test_valid(self) -> None:
        limits = RerankLimits(
            max_documents=256,
            max_query_chars=8000,
            max_document_chars=32000,
            max_total_bytes=4194304,
        )
        assert limits.max_documents == 256

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_documents": 0},
            {"max_query_chars": -1},
            {"max_document_chars": 0},
            {"max_total_bytes": -5},
        ],
    )
    def test_non_positive_rejected(self, kwargs: dict[str, int]) -> None:
        base = {
            "max_documents": 1,
            "max_query_chars": 1,
            "max_document_chars": 1,
            "max_total_bytes": 1,
        }
        base.update(kwargs)
        with pytest.raises(InvalidLimitsError):
            RerankLimits(**base)


class TestRerankResult:
    def test_holds_model_and_items(self) -> None:
        model_id = RerankerModelId(
            name="BAAI/bge-reranker-v2-m3",
            revision="unknown",
            normalized=True,
        )
        items = (
            RankedItem(TextId("a"), 1, RelevanceScore(0.9)),
            RankedItem(TextId("b"), 0, RelevanceScore(0.5)),
        )
        result = RerankResult(model_id=model_id, items=items)
        assert result.model_id.key.endswith("|norm=1")
        assert result.size == 2
        assert result.items[0].text_id.value == "a"
