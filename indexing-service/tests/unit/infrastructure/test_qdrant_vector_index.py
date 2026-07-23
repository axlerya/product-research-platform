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


async def test_set_payload_targets_every_point_of_product():
    """Коммерческие поля и tombstone обязаны лечь на ВСЕ чанки товара.

    Адресация списком id накрыла бы только корневую точку, и чанки
    остались бы со старой ценой и без ``is_deleted``.
    """
    client = FakeClient()
    await _index(client).set_payload(PID, {"price": 9.9})
    op, kw = client.calls[0]
    assert op == "set_payload"
    assert kw["payload"] == {"price": 9.9}
    matched = kw["points"].should
    # чанки — по полю product_id
    assert any(
        getattr(c, "key", None) == "product_id"
        and c.match.value == str(PID.value)
        for c in matched
    )
    # корневая точка — по id: её payload может не нести product_id
    assert any(getattr(c, "has_id", None) == [str(PID.value)] for c in matched)


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


async def test_scroll_watermarks_paginates():
    def _record(seq: int, deleted: bool):
        return SimpleNamespace(
            id=str(UUID(int=seq)),
            payload={
                "aggregate_version": seq,
                "model_version": "m",
                "indexed_at": "2026-07-19T00:00:00+00:00",
                "content_hash": None,
                "is_deleted": deleted,
            },
        )

    class ScrollClient(FakeClient):
        def __init__(self):
            super().__init__()
            self._pages = [
                ([_record(1, False)], "cursor"),
                ([_record(2, True)], None),
            ]
            self._page = 0

        async def scroll(self, **kw):
            page = self._pages[self._page]
            self._page += 1
            return page

    entries = [e async for e in _index(ScrollClient()).scroll_watermarks()]
    assert len(entries) == 2
    assert entries[0].watermark.aggregate_version == 1
    assert entries[1].is_deleted is True


async def test_scroll_watermarks_asks_qdrant_for_root_points_only():
    """Чанк-точки — не товары: reconkile не должен их даже видеть.

    Фильтр «``chunk_ix`` отсутствует или 0», а не «== 0»: синхронный путь
    ``chunk_ix`` не пишет вовсе, и строгое равенство спрятало бы от сверки
    именно те товары, которым ещё не посчитали векторы.
    """

    class ScrollClient(FakeClient):
        async def scroll(self, **kw):
            self.calls.append(("scroll", kw))
            return ([], None)

    client = ScrollClient()
    [e async for e in _index(client).scroll_watermarks()]

    _, kw = client.calls[0]
    condition = kw["scroll_filter"].must_not[0]
    assert condition.key == "chunk_ix"
    assert condition.range.gt == 0
