"""Тесты ``QdrantEmbeddingSink`` на фейковом клиенте (§9.4, без Docker).

Ключевое свойство — merge: async-результат добавляет векторы и водяные
знаки к существующей точке товара, но НЕ затирает коммерческий payload
(цена/остаток/маржа), который пишет синхронный путь.
"""

from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from indexing_service.application.dto.chunk_write import ChunkWrite
from indexing_service.application.dto.embedding_result import SparseData
from indexing_service.application.exceptions import VectorIndexError
from indexing_service.infrastructure.qdrant.embedding_sink import (
    QdrantEmbeddingSink,
)

_POINT = "11111111-1111-1111-1111-111111111111"


def _write(*, content_version: int = 3, dense=(0.1, 0.2), sparse=None):
    return ChunkWrite(
        point_id=_POINT,
        product_id=UUID(int=7),
        sku="PROD-1",
        chunk_ix=0,
        content_version=content_version,
        aggregate_version=2,
        model_version="bge-m3@x|dim=2",
        dense=dense,
        sparse=sparse,
        token_count=11,
    )


class FakeClient:
    """Учитывает вызовы Qdrant; ``records`` — что вернёт ``retrieve``."""

    def __init__(self, records=None) -> None:
        self.calls: list[tuple] = []
        self._records = records or []

    async def retrieve(self, **kw):
        self.calls.append(("retrieve", kw))
        return self._records

    async def upsert(self, **kw):
        self.calls.append(("upsert", kw))

    async def update_vectors(self, **kw):
        self.calls.append(("update_vectors", kw))

    async def set_payload(self, **kw):
        self.calls.append(("set_payload", kw))

    @property
    def ops(self) -> list[str]:
        return [op for op, _ in self.calls]

    def kwargs_of(self, op: str) -> dict:
        return next(kw for name, kw in self.calls if name == op)


def _sink(client) -> QdrantEmbeddingSink:
    return QdrantEmbeddingSink(client, collection="products")


def _stored(**payload):
    return SimpleNamespace(payload=payload)


async def test_absent_point_is_created_with_upsert():
    client = FakeClient(records=[])

    assert await _sink(client).apply_chunk(_write()) is True

    assert client.ops == ["retrieve", "upsert"]
    point = client.kwargs_of("upsert")["points"][0]
    assert point.id == _POINT
    assert point.payload["content_version"] == 3
    assert point.payload["aggregate_version"] == 2


async def test_existing_point_is_merged_not_overwritten():
    client = FakeClient(records=[_stored(content_version=2, price=99.9)])

    assert await _sink(client).apply_chunk(_write()) is True

    # upsert затёр бы price/name/margin — используем merge-операции
    assert "upsert" not in client.ops
    assert client.ops == ["retrieve", "update_vectors", "set_payload"]
    fields = client.kwargs_of("set_payload")["payload"]
    assert fields["content_version"] == 3
    assert "price" not in fields
    assert client.kwargs_of("set_payload")["points"] == [_POINT]


async def test_point_without_content_version_is_merged():
    # Точку создал синхронный путь (payload товара, векторов ещё нет).
    client = FakeClient(records=[_stored(price=10.0, sku="PROD-1")])

    assert await _sink(client).apply_chunk(_write()) is True

    assert "upsert" not in client.ops
    assert "update_vectors" in client.ops


async def test_stale_content_version_is_skipped():
    client = FakeClient(records=[_stored(content_version=9)])

    assert await _sink(client).apply_chunk(_write(content_version=3)) is False

    assert client.ops == ["retrieve"]


async def test_equal_content_version_is_skipped():
    client = FakeClient(records=[_stored(content_version=3)])

    assert await _sink(client).apply_chunk(_write(content_version=3)) is False


async def test_named_vectors_carry_dense_and_sparse():
    client = FakeClient(records=[_stored(content_version=1)])

    await _sink(client).apply_chunk(
        _write(sparse=SparseData(indices=(1, 5), values=(0.5, 0.25)))
    )

    vectors = client.kwargs_of("update_vectors")["points"][0].vector
    assert list(vectors["dense"]) == [0.1, 0.2]
    assert vectors["sparse"].indices == [1, 5]


async def test_merge_without_vectors_skips_update_vectors():
    client = FakeClient(records=[_stored(content_version=1)])

    await _sink(client).apply_chunk(_write(dense=None, sparse=None))

    assert client.ops == ["retrieve", "set_payload"]


async def test_transient_error_translated():
    class Boom(FakeClient):
        async def retrieve(self, **kw):
            raise httpx.ConnectError("qdrant down")

    with pytest.raises(VectorIndexError):
        await _sink(Boom()).apply_chunk(_write())
