"""Unit-тесты векторных VO: DenseVector, SparseVector, EmbeddingModelId,
Embedding. Форма — публичный wire-контракт (dense dim=1024, каноничный
sparse). Только stdlib, без I/O.
"""

import math

import pytest

from embedding_service.domain.exceptions import (
    InvalidModelIdError,
    InvalidVectorError,
)
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.sparse_vector import SparseVector


def _model_id(dim: int = 3) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


class TestDenseVector:
    def test_dimension_equals_length(self) -> None:
        assert DenseVector((0.1, 0.2, 0.3)).dimension == 3

    def test_coerces_ints_to_float(self) -> None:
        dv = DenseVector((1, 2, 3))
        assert all(isinstance(x, float) for x in dv.values)

    def test_empty_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            DenseVector(())

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite_rejected(self, bad: float) -> None:
        with pytest.raises(InvalidVectorError):
            DenseVector((0.1, bad))

    def test_frozen(self) -> None:
        dv = DenseVector((0.1,))
        with pytest.raises((AttributeError, TypeError)):
            dv.values = (0.2,)  # type: ignore[misc]


class TestSparseVector:
    def test_canonical_construction(self) -> None:
        sv = SparseVector((1, 5, 9), (0.3, 0.7, 0.1))
        assert sv.indices == (1, 5, 9)
        assert sv.values == (0.3, 0.7, 0.1)

    def test_empty_allowed(self) -> None:
        sv = SparseVector((), ())
        assert sv.indices == () and sv.values == ()

    def test_length_mismatch_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            SparseVector((1, 2), (0.5,))

    def test_negative_index_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            SparseVector((-1,), (0.5,))

    def test_duplicate_index_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            SparseVector((1, 1), (0.5, 0.6))

    def test_unsorted_index_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            SparseVector((5, 1), (0.5, 0.6))

    @pytest.mark.parametrize("bad", [0.0, math.nan, math.inf])
    def test_zero_or_non_finite_value_rejected(self, bad: float) -> None:
        with pytest.raises(InvalidVectorError):
            SparseVector((1,), (bad,))

    def test_from_mapping_sorts_and_drops_zeros(self) -> None:
        sv = SparseVector.from_mapping({9: 0.1, 1: 0.3, 5: 0.0, 3: 0.7})
        assert sv.indices == (1, 3, 9)
        assert sv.values == (0.3, 0.7, 0.1)

    def test_from_mapping_coerces_str_free_int_keys(self) -> None:
        sv = SparseVector.from_mapping({2: 0.5})
        assert sv.indices == (2,)

    def test_to_mapping_round_trip(self) -> None:
        original = {1: 0.3, 5: 0.7}
        assert SparseVector.from_mapping(original).to_mapping() == original


class TestEmbeddingModelId:
    def test_key_format(self) -> None:
        key = _model_id(1024).key
        assert key == "BAAI/bge-m3@unknown|pool=cls|norm=1|dim=1024"

    def test_key_norm_zero_when_not_normalized(self) -> None:
        mid = EmbeddingModelId(
            name="m", revision="r", pooling="mean", normalized=False, dim=8
        )
        assert mid.key == "m@r|pool=mean|norm=0|dim=8"

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(InvalidModelIdError):
            EmbeddingModelId(
                name="  ", revision="r", pooling="cls", normalized=True, dim=8
            )

    @pytest.mark.parametrize("dim", [0, -1])
    def test_non_positive_dim_rejected(self, dim: int) -> None:
        with pytest.raises(InvalidModelIdError):
            EmbeddingModelId(
                name="m", revision="r", pooling="cls", normalized=True, dim=dim
            )


class TestEmbedding:
    def test_valid_dims_match(self) -> None:
        emb = Embedding(
            dense=DenseVector((0.1, 0.2, 0.3)),
            sparse=SparseVector((1,), (0.5,)),
            model_id=_model_id(3),
        )
        assert emb.dense.dimension == emb.model_id.dim

    def test_dim_mismatch_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            Embedding(
                dense=DenseVector((0.1, 0.2)),
                sparse=SparseVector((), ()),
                model_id=_model_id(3),
            )
