"""Тесты value object ``SparseVector`` (разрежённый эмбеддинг BGE-M3).

Каноническая форма: индексы отсортированы, уникальны, неотрицательны;
значения конечны и ненулевы (нули отбрасываются, как делает BGE-M3).
"""

import pytest

from indexing_service.domain.exceptions import InvalidVectorError
from indexing_service.domain.value_objects.sparse_vector import SparseVector


def test_from_mapping_sorts_and_drops_zeros():
    sparse = SparseVector.from_mapping({5: 0.3, 1: 0.7, 3: 0.0})
    assert sparse.indices == (1, 5)
    assert sparse.values == (0.7, 0.3)


def test_to_mapping_roundtrip():
    sparse = SparseVector.from_mapping({1: 0.7, 5: 0.3})
    assert sparse.to_mapping() == {1: 0.7, 5: 0.3}


def test_empty_is_allowed():
    assert SparseVector(indices=(), values=()).indices == ()


def test_length_mismatch_rejected():
    with pytest.raises(InvalidVectorError):
        SparseVector(indices=(1, 2), values=(0.5,))


def test_rejects_duplicate_indices():
    with pytest.raises(InvalidVectorError):
        SparseVector(indices=(1, 1), values=(0.5, 0.6))


def test_rejects_negative_index():
    with pytest.raises(InvalidVectorError):
        SparseVector(indices=(-1,), values=(0.5,))


def test_rejects_unsorted_indices():
    with pytest.raises(InvalidVectorError):
        SparseVector(indices=(2, 1), values=(0.5, 0.6))


def test_rejects_zero_value():
    with pytest.raises(InvalidVectorError):
        SparseVector(indices=(1,), values=(0.0,))
