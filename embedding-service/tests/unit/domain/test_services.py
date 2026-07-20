"""Unit-тесты доменных сервисов: BatchGuard, EmbeddingAssembler,
EmbeddingValidator. Чистые функции, без I/O.
"""

import pytest

from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    EmptyBatchError,
    InvalidVectorError,
    RequestTooLargeError,
    TextTooLongError,
)
from embedding_service.domain.services.assembler import EmbeddingAssembler
from embedding_service.domain.services.batch_guard import BatchGuard
from embedding_service.domain.services.validator import EmbeddingValidator
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
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)
from embedding_service.domain.value_objects.sparse_vector import SparseVector
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount


def _model_id(dim: int = 2) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


def _embedding(dim: int = 2) -> Embedding:
    return Embedding(
        dense=DenseVector(tuple(0.1 for _ in range(dim))),
        sparse=SparseVector((1,), (0.5,)),
        model_id=_model_id(dim),
    )


def _item(text: str, text_id: str = "id") -> EmbeddingRequestItem:
    return EmbeddingRequestItem(TextId(text_id), EmbeddingText(text))


def _limits(
    *,
    max_texts: int = 10,
    max_text_chars: int = 100,
    max_tokens: int = 8192,
    max_total_bytes: int = 10_000,
) -> EmbeddingLimits:
    return EmbeddingLimits(
        max_texts=max_texts,
        max_text_chars=max_text_chars,
        max_tokens=max_tokens,
        max_total_bytes=max_total_bytes,
    )


class TestBatchGuard:
    def test_valid_batch_passes(self) -> None:
        BatchGuard.validate([_item("hello"), _item("world")], _limits())

    def test_empty_batch_rejected(self) -> None:
        with pytest.raises(EmptyBatchError):
            BatchGuard.validate([], _limits())

    def test_too_many_texts_rejected(self) -> None:
        items = [_item("x", str(i)) for i in range(3)]
        with pytest.raises(BatchTooLargeError):
            BatchGuard.validate(items, _limits(max_texts=2))

    def test_too_long_text_rejected(self) -> None:
        with pytest.raises(TextTooLongError):
            BatchGuard.validate([_item("x" * 11)], _limits(max_text_chars=10))

    def test_total_bytes_exceeded_rejected(self) -> None:
        # два русских текста: каждая кириллическая буква — 2 байта UTF-8.
        items = [_item("абвгд", "a"), _item("абвгд", "b")]
        with pytest.raises(RequestTooLargeError):
            BatchGuard.validate(items, _limits(max_total_bytes=15))

    def test_bytes_boundary_ok(self) -> None:
        # ровно на границе — проходит (строгое `>`).
        BatchGuard.validate([_item("hello")], _limits(max_total_bytes=5))

    def test_does_not_check_tokens(self) -> None:
        # токен-лимит не проверяется в домене (нет токенайзера) — только чары.
        BatchGuard.validate([_item("a" * 50)], _limits(max_tokens=1))


class TestEmbeddingAssembler:
    def test_preserves_order_mixed_ok_error(self) -> None:
        text_ids = [TextId("a"), TextId("b"), TextId("c")]
        outcomes = [
            (_embedding(), TokenCount(3)),
            ItemError(EmbeddingErrorCode.TEXT_TOO_LONG, "long"),
            (_embedding(), TokenCount(5)),
        ]
        result = EmbeddingAssembler.assemble(text_ids, outcomes, _model_id())
        assert [item.text_id.value for item in result.items] == ["a", "b", "c"]
        assert result.items[0].is_ok
        assert not result.items[1].is_ok
        assert result.items[1].error is not None
        assert result.items[2].token_count == TokenCount(5)
        assert result.model_id == _model_id()
        assert result.has_errors

    def test_all_ok(self) -> None:
        result = EmbeddingAssembler.assemble(
            [TextId("a")], [(_embedding(), TokenCount(1))], _model_id()
        )
        assert result.all_ok

    def test_length_mismatch_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            EmbeddingAssembler.assemble(
                [TextId("a"), TextId("b")],
                [(_embedding(), TokenCount(1))],
                _model_id(),
            )

    def test_empty_assemble(self) -> None:
        result = EmbeddingAssembler.assemble([], [], _model_id())
        assert result.items == ()
        assert result.all_ok  # пустой батч — вырожденно «все ок»


class TestEmbeddingValidator:
    def test_uniform_batch_passes(self) -> None:
        EmbeddingValidator.validate_batch(
            [_embedding(2), _embedding(2)],
            expected_dim=2,
            model_id=_model_id(2),
        )

    def test_wrong_dimension_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            EmbeddingValidator.validate_batch(
                [_embedding(2)], expected_dim=3, model_id=_model_id(2)
            )

    def test_foreign_model_rejected(self) -> None:
        other = EmbeddingModelId(
            name="other", revision="r", pooling="cls", normalized=True, dim=2
        )
        with pytest.raises(InvalidVectorError):
            EmbeddingValidator.validate_batch(
                [_embedding(2)], expected_dim=2, model_id=other
            )

    def test_empty_batch_ok(self) -> None:
        EmbeddingValidator.validate_batch(
            [], expected_dim=2, model_id=_model_id(2)
        )
