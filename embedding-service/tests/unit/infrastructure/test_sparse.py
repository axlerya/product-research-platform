"""Unit-тесты конвертации lexical_weights BGE-M3 → SparseVector."""

from embedding_service.infrastructure.embedding.sparse import (
    lexical_weights_to_sparse,
)


def test_str_keys_sorted_and_zeros_dropped() -> None:
    sparse = lexical_weights_to_sparse({"9": 0.1, "1": 0.3, "5": 0.0})
    assert sparse.indices == (1, 9)
    assert sparse.values == (0.3, 0.1)


def test_empty_mapping() -> None:
    sparse = lexical_weights_to_sparse({})
    assert sparse.indices == ()
    assert sparse.values == ()
