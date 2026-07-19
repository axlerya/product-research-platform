"""In-memory фейки портов для unit-тестов прикладного слоя.

``FakeVectorIndex`` хранит точки как payload + признак наличия векторов;
водяной знак восстанавливается из payload (как реальный адаптер читает
его из Qdrant). ``FakeEmbeddingModel`` детерминирован и не грузит модель.
"""

import hashlib
from datetime import UTC, datetime

from indexing_service.application.dto.point import PointRecord
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.domain.value_objects.sparse_vector import SparseVector
from indexing_service.domain.value_objects.watermark import IndexingWatermark

_FALLBACK_TIME = datetime(2000, 1, 1, tzinfo=UTC)


def _watermark(payload: dict) -> IndexingWatermark:
    content_hash = payload.get("content_hash")
    indexed_at = payload.get("indexed_at")
    return IndexingWatermark(
        aggregate_version=int(payload["aggregate_version"]),
        model_version=str(payload.get("model_version", "")),
        content_hash=ContentHash(content_hash) if content_hash else None,
        indexed_at=(
            datetime.fromisoformat(indexed_at)
            if isinstance(indexed_at, str)
            else _FALLBACK_TIME
        ),
    )


class FakeVectorIndex:
    """In-memory ``VectorIndex``: точка = payload + признак векторов."""

    def __init__(self) -> None:
        self._points: dict[ProductId, dict] = {}
        self.upserts: list[PointRecord] = []
        self.vector_updates: list[ProductId] = []
        self.payload_sets: list[tuple[ProductId, dict]] = []

    def preload(self, product_id: ProductId, payload: dict) -> None:
        self._points[product_id] = {"payload": dict(payload), "vectors": True}

    async def get_watermark(
        self, product_id: ProductId
    ) -> IndexingWatermark | None:
        entry = self._points.get(product_id)
        return _watermark(entry["payload"]) if entry else None

    async def upsert_document(self, point: PointRecord) -> None:
        self._points[point.product_id] = {
            "payload": dict(point.payload),
            "vectors": True,
        }
        self.upserts.append(point)

    async def update_vectors(self, product_id, embedding) -> None:
        entry = self._points.setdefault(
            product_id, {"payload": {}, "vectors": False}
        )
        entry["vectors"] = True
        self.vector_updates.append(product_id)

    async def set_payload(self, product_id, fields) -> None:
        entry = self._points.setdefault(
            product_id, {"payload": {}, "vectors": False}
        )
        entry["payload"].update(fields)
        self.payload_sets.append((product_id, dict(fields)))

    def payload_of(self, product_id: ProductId) -> dict:
        return self._points[product_id]["payload"]

    def exists(self, product_id: ProductId) -> bool:
        return product_id in self._points


class FakeEmbeddingModel:
    """Детерминированный фейк ``EmbeddingModel`` (dim=4, без загрузки)."""

    _MODEL = EmbeddingModelId("fake", "v1", "cls", normalized=True, dim=4)

    def __init__(self) -> None:
        self.calls = 0

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._MODEL

    async def embed_documents(
        self, texts: list[SearchText]
    ) -> list[Embedding]:
        self.calls += 1
        return [self._embed(text) for text in texts]

    def _embed(self, text: SearchText) -> Embedding:
        digest = hashlib.sha256(text.value.encode("utf-8")).digest()
        dense = DenseVector(tuple(digest[i] / 255.0 for i in range(4)))
        sparse = SparseVector.from_mapping({1: 0.5, 2: 0.25})
        return Embedding(dense=dense, sparse=sparse, model_id=self._MODEL)


class FakeCatalogGateway:
    """In-memory ``CatalogGateway``."""

    def __init__(self, snapshots=None) -> None:
        self._by_id = {
            ProductId(snapshot.product_id): snapshot
            for snapshot in (snapshots or [])
        }

    async def get_product(self, product_id: ProductId):
        return self._by_id.get(product_id)

    async def _iter(self):
        for snapshot in self._by_id.values():
            yield snapshot

    def iter_products(self, *, batch: int = 100):
        return self._iter()


class FixedClock:
    """``Clock`` с фиксированным моментом."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment
