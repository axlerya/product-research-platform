"""Тесты value object ``DenseVector`` (плотный эмбеддинг)."""

import pytest

from indexing_service.domain.exceptions import InvalidVectorError
from indexing_service.domain.value_objects.dense_vector import DenseVector


def test_dimension():
    assert DenseVector((0.1, 0.2, 0.3)).dimension == 3


def test_coerces_sequence_to_float_tuple():
    vector = DenseVector([1, 2, 3])
    assert vector.values == (1.0, 2.0, 3.0)


def test_rejects_empty():
    with pytest.raises(InvalidVectorError):
        DenseVector(())


def test_rejects_non_finite():
    with pytest.raises(InvalidVectorError):
        DenseVector((0.1, float("nan")))


def test_equality_by_values():
    assert DenseVector((0.1, 0.2)) == DenseVector((0.1, 0.2))
