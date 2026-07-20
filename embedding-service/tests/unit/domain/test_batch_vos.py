"""Unit-тесты батч-VO: EmbeddingRequestItem, ItemError/EmbeddingErrorCode,
EmbeddingItemResult, BatchEmbeddingResult, EmbeddingLimits, ContractVersion.
"""

import pytest

from embedding_service.domain.exceptions import (
    InvalidLimitsError,
    InvalidVectorError,
)
from embedding_service.domain.value_objects.batch_result import (
    BatchEmbeddingResult,
)
from embedding_service.domain.value_objects.contract_version import (
    ContractVersion,
)
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.item_error import (
    EmbeddingErrorCode,
    ItemError,
)
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)
from embedding_service.domain.value_objects.sparse_vector import SparseVector
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount


def _model_id() -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=2,
    )


def _embedding() -> Embedding:
    return Embedding(
        dense=DenseVector((0.1, 0.2)),
        sparse=SparseVector((1,), (0.5,)),
        model_id=_model_id(),
    )


class TestRequestItem:
    def test_holds_id_and_text(self) -> None:
        item = EmbeddingRequestItem(TextId("id-1"), EmbeddingText("hi"))
        assert item.text_id.value == "id-1"
        assert item.text.value == "hi"


class TestItemError:
    def test_holds_code_and_message(self) -> None:
        err = ItemError(EmbeddingErrorCode.EMPTY_TEXT, "пусто")
        assert err.code is EmbeddingErrorCode.EMPTY_TEXT
        assert err.message == "пусто"

    def test_error_codes(self) -> None:
        assert {c.value for c in EmbeddingErrorCode} == {
            "EMPTY_TEXT",
            "TEXT_TOO_LONG",
            "TOKENS_EXCEEDED",
            "INFERENCE_FAILED",
        }


class TestItemResult:
    def test_ok_factory(self) -> None:
        res = EmbeddingItemResult.ok(
            TextId("id-1"), _embedding(), TokenCount(5)
        )
        assert res.is_ok
        assert res.embedding is not None
        assert res.token_count == TokenCount(5)
        assert res.error is None

    def test_failed_factory(self) -> None:
        res = EmbeddingItemResult.failed(
            TextId("id-2"), ItemError(EmbeddingErrorCode.EMPTY_TEXT, "x")
        )
        assert not res.is_ok
        assert res.embedding is None
        assert res.error is not None

    def test_both_set_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            EmbeddingItemResult(
                text_id=TextId("id"),
                embedding=_embedding(),
                error=ItemError(EmbeddingErrorCode.INFERENCE_FAILED, "x"),
            )

    def test_neither_set_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            EmbeddingItemResult(text_id=TextId("id"))


class TestBatchResult:
    def test_all_ok(self) -> None:
        batch = BatchEmbeddingResult(
            model_id=_model_id(),
            items=(
                EmbeddingItemResult.ok(
                    TextId("a"), _embedding(), TokenCount(1)
                ),
                EmbeddingItemResult.ok(
                    TextId("b"), _embedding(), TokenCount(2)
                ),
            ),
        )
        assert batch.all_ok
        assert not batch.has_errors

    def test_has_errors(self) -> None:
        batch = BatchEmbeddingResult(
            model_id=_model_id(),
            items=(
                EmbeddingItemResult.ok(
                    TextId("a"), _embedding(), TokenCount(1)
                ),
                EmbeddingItemResult.failed(
                    TextId("b"),
                    ItemError(EmbeddingErrorCode.TEXT_TOO_LONG, "long"),
                ),
            ),
        )
        assert not batch.all_ok
        assert batch.has_errors


class TestEmbeddingLimits:
    def test_valid(self) -> None:
        limits = EmbeddingLimits(
            max_texts=256,
            max_text_chars=32000,
            max_tokens=8192,
            max_total_bytes=4194304,
        )
        assert limits.max_texts == 256

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_texts": 0},
            {"max_text_chars": -1},
            {"max_tokens": 0},
            {"max_total_bytes": -5},
        ],
    )
    def test_non_positive_rejected(self, kwargs: dict[str, int]) -> None:
        base = {
            "max_texts": 1,
            "max_text_chars": 1,
            "max_tokens": 1,
            "max_total_bytes": 1,
        }
        base.update(kwargs)
        with pytest.raises(InvalidLimitsError):
            EmbeddingLimits(**base)


class TestContractVersion:
    def test_wire_string(self) -> None:
        assert ContractVersion(1, 0).wire == "1.0"
        assert ContractVersion(2, 3).wire == "2.3"
