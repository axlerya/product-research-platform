"""Тесты адаптера ``QdrantVectorIndex`` на фейковом клиенте (без Docker)."""

from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from indexing_service.application.dto.point import PointRecord
from indexing_service.application.exceptions import VectorIndexError
from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.sparse_vector import SparseVector
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)

PID = ProductId(UUID(int=9))
_MODEL = EmbeddingModelId("m", "r", "cls", normalized=True, dim=4)


def _embedding() -> Embedding:
    return Embedding(
        dense=DenseVector((0.1, 0.2, 0.3, 0.4)),
        sparse=SparseVector.from_mapping({1: 0.5}),
        model_id=_MODEL,
    )


class FakeClient:
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


def _index(client) -> QdrantVectorIndex:
    return QdrantVectorIndex(client, collection="products")


async def test_get_watermark_none_when_absent():
    assert await _index(FakeClient(records=[])).get_watermark(PID) is None


async def test_get_watermark_parses_payload():
    record = SimpleNamespace(
        payload={
            "aggregate_version": 6,
            "model_version": "m",
            "indexed_at": "2026-07-19T00:00:00+00:00",
            "content_hash": None,
        }
    )
    watermark = await _index(FakeClient(records=[record])).get_watermark(PID)
    assert watermark.aggregate_version == 6


async def test_upsert_sends_point_struct():
    client = FakeClient()
    point = PointRecord(
        product_id=PID, embedding=_embedding(), payload={"price": 1.0}
    )
    await _index(client).upsert_document(point)
    op, kw = client.calls[0]
    assert op == "upsert"
    assert kw["collection_name"] == "products"
    assert kw["points"][0].id == str(PID.value)


async def test_set_payload_targets_point_id():
    client = FakeClient()
    await _index(client).set_payload(PID, {"price": 9.9})
    op, kw = client.calls[0]
    assert op == "set_payload"
    assert kw["payload"] == {"price": 9.9}
    assert kw["points"] == [str(PID.value)]


async def test_update_vectors_sends_named_vectors():
    client = FakeClient()
    await _index(client).update_vectors(PID, _embedding())
    op, kw = client.calls[0]
    assert op == "update_vectors"
    assert kw["points"][0].id == str(PID.value)


async def test_transient_error_translated():
    class Boom(FakeClient):
        async def upsert(self, **kw):
            raise httpx.ConnectError("qdrant down")

    point = PointRecord(product_id=PID, embedding=_embedding(), payload={})
    with pytest.raises(VectorIndexError):
        await _index(Boom()).upsert_document(point)
