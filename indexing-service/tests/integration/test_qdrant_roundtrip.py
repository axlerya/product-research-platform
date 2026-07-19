"""Integration: адаптер Qdrant против реального Qdrant (testcontainers)."""

from uuid import uuid4

import pytest
from qdrant_client import models

from indexing_service.application.dto.point import PointRecord
from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.sparse_vector import SparseVector
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)

pytestmark = pytest.mark.integration

_MODEL = EmbeddingModelId("m", "r", "cls", normalized=True, dim=4)


def _embedding() -> Embedding:
    return Embedding(
        dense=DenseVector((0.1, 0.2, 0.3, 0.4)),
        sparse=SparseVector.from_mapping({1: 0.5, 3: 0.2}),
        model_id=_MODEL,
    )


def _payload(version: int = 1) -> dict:
    return {
        "aggregate_version": version,
        "model_version": "m",
        "content_hash": "h" * 64,
        "indexed_at": "2026-07-19T00:00:00+00:00",
        "price": 10.0,
        "is_deleted": False,
    }


async def test_upsert_watermark_and_set_payload_preserves_vectors(
    qdrant_client,
):
    collection = f"products_it_{uuid4().hex[:8]}"
    await CollectionProvisioner(
        qdrant_client, collection=collection, dim=4
    ).ensure()
    index = QdrantVectorIndex(qdrant_client, collection=collection)
    pid = ProductId.new()

    await index.upsert_document(
        PointRecord(product_id=pid, embedding=_embedding(), payload=_payload())
    )

    watermark = await index.get_watermark(pid)
    assert watermark is not None
    assert watermark.aggregate_version == 1

    # Ключевой инвариант §6.3: set_payload мержит и НЕ трогает векторы.
    await index.set_payload(pid, {"price": 19.99})
    records = await qdrant_client.retrieve(
        collection_name=collection,
        ids=[str(pid.value)],
        with_payload=True,
        with_vectors=True,
    )
    assert records[0].payload["price"] == 19.99
    assert records[0].payload["aggregate_version"] == 1  # merge сохранил
    assert "dense" in records[0].vector  # векторы на месте
    assert "sparse" in records[0].vector

    entries = [e async for e in index.scroll_watermarks()]
    assert len(entries) == 1
    assert entries[0].product_id == pid


async def test_alias_swap_and_hybrid_query(qdrant_client):
    collection = f"products_hy_{uuid4().hex[:8]}"
    alias = f"alias_{uuid4().hex[:8]}"
    provisioner = CollectionProvisioner(
        qdrant_client, collection=collection, dim=4
    )
    await provisioner.ensure()
    await provisioner.point_alias(alias)

    # Пишем через alias — как это делает консюмер.
    index = QdrantVectorIndex(qdrant_client, collection=alias)
    pid = ProductId.new()
    await index.upsert_document(
        PointRecord(product_id=pid, embedding=_embedding(), payload=_payload())
    )

    # Hybrid Query API (кросс-сервисный контракт с search-service).
    result = await qdrant_client.query_points(
        collection_name=alias,
        prefetch=[
            models.Prefetch(
                query=[0.1, 0.2, 0.3, 0.4], using="dense", limit=10
            ),
            models.Prefetch(
                query=models.SparseVector(indices=[1, 3], values=[0.5, 0.2]),
                using="sparse",
                limit=10,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=5,
        with_payload=True,
    )
    assert len(result.points) == 1
    assert result.points[0].payload["aggregate_version"] == 1
