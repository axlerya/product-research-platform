"""Тесты мапперов Qdrant (домен → модели qdrant-client)."""

from uuid import UUID

from qdrant_client import models

from indexing_service.application.dto.point import PointRecord
from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.sparse_vector import SparseVector
from indexing_service.infrastructure.qdrant.collection_spec import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
)
from indexing_service.infrastructure.qdrant.mappers import (
    point_id,
    to_named_vectors,
    to_point_struct,
    to_sparse_vector,
    watermark_from_payload,
)

_MODEL = EmbeddingModelId("m", "r", "cls", normalized=True, dim=4)


def _embedding() -> Embedding:
    return Embedding(
        dense=DenseVector((0.1, 0.2, 0.3, 0.4)),
        sparse=SparseVector.from_mapping({7: 0.5, 3: 0.2}),
        model_id=_MODEL,
    )


def test_point_id_is_uuid_string():
    pid = ProductId(UUID("0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a"))
    assert point_id(pid) == "0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a"


def test_to_sparse_vector_sorted():
    sparse = to_sparse_vector(SparseVector.from_mapping({7: 0.5, 3: 0.2}))
    assert isinstance(sparse, models.SparseVector)
    assert sparse.indices == [3, 7]
    assert sparse.values == [0.2, 0.5]


def test_to_named_vectors_keys():
    named = to_named_vectors(_embedding())
    assert set(named) == {DENSE_VECTOR, SPARSE_VECTOR}
    assert named[DENSE_VECTOR] == [0.1, 0.2, 0.3, 0.4]
    assert isinstance(named[SPARSE_VECTOR], models.SparseVector)


def test_to_point_struct():
    pid = ProductId(UUID(int=5))
    point = PointRecord(
        product_id=pid, embedding=_embedding(), payload={"price": 1.0}
    )
    struct = to_point_struct(point)
    assert struct.id == str(pid.value)
    assert struct.payload == {"price": 1.0}
    assert DENSE_VECTOR in struct.vector


def test_watermark_from_payload():
    watermark = watermark_from_payload(
        {
            "aggregate_version": 6,
            "model_version": "m@v",
            "content_hash": "a" * 64,
            "indexed_at": "2026-07-19T10:15:30+00:00",
        }
    )
    assert watermark.aggregate_version == 6
    assert watermark.model_version == "m@v"
    assert watermark.content_hash.value == "a" * 64


def test_watermark_none_without_version():
    assert watermark_from_payload(None) is None
    assert watermark_from_payload({}) is None


def test_watermark_content_hash_optional():
    watermark = watermark_from_payload(
        {"aggregate_version": 1, "indexed_at": "2026-07-19T00:00:00+00:00"}
    )
    assert watermark.content_hash is None
    assert watermark.model_version == ""
