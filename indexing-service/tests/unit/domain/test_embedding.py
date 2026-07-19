"""Тесты value object ``Embedding`` (dense + sparse + модель)."""

import pytest

from indexing_service.domain.exceptions import InvalidVectorError
from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.sparse_vector import SparseVector

_MODEL = EmbeddingModelId("BAAI/bge-m3", "rev", "cls", normalized=True, dim=3)


def test_holds_vectors_and_model():
    embedding = Embedding(
        dense=DenseVector((0.1, 0.2, 0.3)),
        sparse=SparseVector.from_mapping({1: 0.5}),
        model_id=_MODEL,
    )
    assert embedding.dense.dimension == 3
    assert embedding.model_id is _MODEL


def test_dim_mismatch_rejected():
    with pytest.raises(InvalidVectorError):
        Embedding(
            dense=DenseVector((0.1, 0.2)),
            sparse=SparseVector(indices=(), values=()),
            model_id=_MODEL,
        )
