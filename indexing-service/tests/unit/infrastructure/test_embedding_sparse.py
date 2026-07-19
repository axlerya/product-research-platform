"""Тесты конвертации lexical_weights → SparseVector."""

from indexing_service.infrastructure.embedding.sparse import (
    lexical_weights_to_sparse,
)


def test_converts_str_tokens_to_int_indices():
    sparse = lexical_weights_to_sparse({"7": 0.5, "3": 0.2})
    assert sparse.indices == (3, 7)
    assert sparse.values == (0.2, 0.5)


def test_drops_zero_weights():
    sparse = lexical_weights_to_sparse({"1": 0.0, "2": 0.9})
    assert sparse.indices == (2,)
    assert sparse.values == (0.9,)


def test_empty_weights():
    assert lexical_weights_to_sparse({}).indices == ()
