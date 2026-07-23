"""Integration: ``QdrantEmbeddingSink`` против реального Qdrant (§9.4).

Проверяем запись точки чанка с двумя водяными знаками и guard по
``content_version`` (устаревший результат не затирает свежий текст).
"""

from uuid import uuid4

import pytest

from indexing_service.application.dto.chunk_write import ChunkWrite
from indexing_service.application.dto.embedding_result import SparseData
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.embedding_sink import (
    QdrantEmbeddingSink,
)

pytestmark = pytest.mark.integration


def _write(
    point_id: str, *, content_version: int, collection: str | None = None
) -> ChunkWrite:
    return ChunkWrite(
        point_id=point_id,
        product_id=uuid4(),
        sku="PROD-1",
        chunk_ix=0,
        content_version=content_version,
        aggregate_version=2,
        content_hash="a" * 64,
        model_version="bge-m3@x|dim=4",
        dense=(0.1, 0.2, 0.3, 0.4),
        sparse=SparseData(indices=(1, 3), values=(0.5, 0.2)),
        token_count=11,
        collection=collection,
    )


async def _provision(qdrant_client, prefix: str = "chunks_it") -> str:
    collection = f"{prefix}_{uuid4().hex[:8]}"
    await CollectionProvisioner(
        qdrant_client, collection=collection, dim=4
    ).ensure()
    return collection


async def _sink(qdrant_client):
    collection = await _provision(qdrant_client)
    sink = QdrantEmbeddingSink(qdrant_client, default_collection=collection)
    return sink, collection


async def _payload(qdrant_client, collection, point_id):
    records = await qdrant_client.retrieve(
        collection_name=collection,
        ids=[point_id],
        with_payload=True,
        with_vectors=True,
    )
    return records[0]


async def test_apply_writes_two_watermarks_and_vectors(qdrant_client):
    sink, collection = await _sink(qdrant_client)
    point_id = str(uuid4())

    applied = await sink.apply_chunk(_write(point_id, content_version=5))

    assert applied is True
    record = await _payload(qdrant_client, collection, point_id)
    assert record.payload["content_version"] == 5
    assert record.payload["aggregate_version"] == 2
    assert record.payload["model_version"] == "bge-m3@x|dim=4"
    assert record.payload["sku"] == "PROD-1"
    assert record.payload["chunk_ix"] == 0
    assert "dense" in record.vector
    assert "sparse" in record.vector


async def test_stale_content_version_is_skipped(qdrant_client):
    sink, collection = await _sink(qdrant_client)
    point_id = str(uuid4())

    assert await sink.apply_chunk(_write(point_id, content_version=6)) is True
    # старее → пропуск, свежая версия не затирается
    assert await sink.apply_chunk(_write(point_id, content_version=5)) is False
    record = await _payload(qdrant_client, collection, point_id)
    assert record.payload["content_version"] == 6


async def test_equal_content_version_is_skipped(qdrant_client):
    sink, _ = await _sink(qdrant_client)
    point_id = str(uuid4())

    assert await sink.apply_chunk(_write(point_id, content_version=3)) is True
    assert await sink.apply_chunk(_write(point_id, content_version=3)) is False


async def test_newer_content_version_overwrites(qdrant_client):
    sink, collection = await _sink(qdrant_client)
    point_id = str(uuid4())

    assert await sink.apply_chunk(_write(point_id, content_version=2)) is True
    assert await sink.apply_chunk(_write(point_id, content_version=7)) is True
    record = await _payload(qdrant_client, collection, point_id)
    assert record.payload["content_version"] == 7


async def test_merge_keeps_commercial_payload(qdrant_client):
    """Векторы дописываются к точке товара, не снося цену/остаток (§9.4)."""
    sink, collection = await _sink(qdrant_client)
    point_id = str(uuid4())
    # Точку создал синхронный путь: коммерческий payload, векторов нет.
    await qdrant_client.upsert(
        collection_name=collection,
        points=[
            {
                "id": point_id,
                "vector": {},
                "payload": {"price": 99.9, "stock": 5, "name": "Кружка"},
            }
        ],
    )

    assert await sink.apply_chunk(_write(point_id, content_version=4)) is True

    record = await _payload(qdrant_client, collection, point_id)
    assert record.payload["price"] == 99.9
    assert record.payload["stock"] == 5
    assert record.payload["name"] == "Кружка"
    assert record.payload["content_version"] == 4
    assert "dense" in record.vector


# --- Маршрутизация записи по коллекции эпохи reindex ---


async def test_reindex_write_lands_in_target_not_in_alias(qdrant_client):
    """Результат эпохи пишется в целевую коллекцию, живой alias не тронут."""
    alias_collection = await _provision(qdrant_client, "alias_it")
    target = await _provision(qdrant_client, "epoch_it")
    sink = QdrantEmbeddingSink(
        qdrant_client, default_collection=alias_collection
    )
    point_id = str(uuid4())

    applied = await sink.apply_chunk(
        _write(point_id, content_version=5, collection=target)
    )

    assert applied is True
    written = await _payload(qdrant_client, target, point_id)
    assert written.payload["content_version"] == 5
    assert "dense" in written.vector
    # в живом alias точки не появилось
    assert (
        await qdrant_client.retrieve(
            collection_name=alias_collection, ids=[point_id]
        )
        == []
    )


async def test_reindex_write_stamps_epoch_marker(qdrant_client):
    """Метка эпохи ложится в payload вместе с векторами (гейт свапа)."""
    target = await _provision(qdrant_client, "epoch_it")
    sink = QdrantEmbeddingSink(
        qdrant_client, default_collection=await _provision(qdrant_client)
    )
    point_id = str(uuid4())

    await sink.apply_chunk(
        _write(point_id, content_version=5, collection=target)
    )

    record = await _payload(qdrant_client, target, point_id)
    assert record.payload["reindex_epoch"] == target


async def test_guard_compares_versions_within_target_collection(
    qdrant_client,
):
    """Свежая версия в alias не мешает записать эпоху в новую коллекцию."""
    alias_collection = await _provision(qdrant_client, "alias_it")
    target = await _provision(qdrant_client, "epoch_it")
    sink = QdrantEmbeddingSink(
        qdrant_client, default_collection=alias_collection
    )
    point_id = str(uuid4())
    # В alias уже лежит более свежая версия того же чанка.
    await sink.apply_chunk(_write(point_id, content_version=9))

    applied = await sink.apply_chunk(
        _write(point_id, content_version=5, collection=target)
    )

    assert applied is True
    record = await _payload(qdrant_client, target, point_id)
    assert record.payload["content_version"] == 5
