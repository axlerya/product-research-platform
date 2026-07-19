"""Чистые мапперы: домен → модели qdrant-client и обратно."""

from datetime import UTC, datetime

from qdrant_client import models

from indexing_service.application.dto.point import PointRecord
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.sparse_vector import SparseVector
from indexing_service.domain.value_objects.watermark import IndexingWatermark
from indexing_service.infrastructure.qdrant.collection_spec import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def point_id(product_id: ProductId) -> str:
    """id точки Qdrant = UUID товара строкой."""
    return str(product_id.value)


def to_sparse_vector(sparse: SparseVector) -> models.SparseVector:
    """Домен → ``models.SparseVector``."""
    return models.SparseVector(
        indices=list(sparse.indices), values=list(sparse.values)
    )


def to_named_vectors(embedding: Embedding) -> dict[str, object]:
    """Домен → словарь named-векторов ``{dense, sparse}``."""
    return {
        DENSE_VECTOR: list(embedding.dense.values),
        SPARSE_VECTOR: to_sparse_vector(embedding.sparse),
    }


def to_point_struct(point: PointRecord) -> models.PointStruct:
    """``PointRecord`` → ``models.PointStruct`` для upsert."""
    return models.PointStruct(
        id=point_id(point.product_id),
        vector=to_named_vectors(point.embedding),
        payload=dict(point.payload),
    )


def watermark_from_payload(
    payload: dict | None,
) -> IndexingWatermark | None:
    """Восстанавливает водяной знак из payload точки (или ``None``)."""
    if not payload or "aggregate_version" not in payload:
        return None
    content_hash = payload.get("content_hash")
    indexed_at = payload.get("indexed_at")
    return IndexingWatermark(
        aggregate_version=int(payload["aggregate_version"]),
        model_version=str(payload.get("model_version", "")),
        content_hash=ContentHash(content_hash) if content_hash else None,
        indexed_at=(
            datetime.fromisoformat(indexed_at)
            if isinstance(indexed_at, str)
            else _EPOCH
        ),
    )
