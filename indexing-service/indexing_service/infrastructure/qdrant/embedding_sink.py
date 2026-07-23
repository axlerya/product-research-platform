"""Адаптер ``QdrantEmbeddingSink`` — реализация порта ``EmbeddingResultSink``.

Пишет точку чанка (ключ — ``point_id``) с двумя водяными знаками
(``aggregate_version`` + ``content_version``, §9.4). Guard по
``content_version``: результат старее уже записанного — пропускаем (не
затираем свежий текст).

Семантика записи — **merge**: если точка уже есть, дописываем векторы
(``update_vectors``) и знаки (``set_payload``), не трогая остальной payload;
``upsert`` применяем только к отсутствующей точке. Иначе async-результат снёс
бы коммерческие поля товара (цена/остаток/маржа), которые пишет синхронный
путь. Инфраструктурные сбои → ``VectorIndexError`` (ретрай).
"""

from datetime import UTC, datetime

import httpx
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)

from indexing_service.application.dto.chunk_write import ChunkWrite
from indexing_service.application.exceptions import VectorIndexError
from indexing_service.infrastructure.qdrant.collection_spec import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
)

_QDRANT_ERRORS = (
    UnexpectedResponse,
    ResponseHandlingException,
    httpx.HTTPError,
    OSError,
)


class QdrantEmbeddingSink:
    """Пишет точки чанков в коллекцию (async-путь), guard по версии текста."""

    def __init__(
        self, client: AsyncQdrantClient, *, collection: str
    ) -> None:
        self._client = client
        self._collection = collection

    async def apply_chunk(self, write: ChunkWrite) -> bool:
        """Пишет точку чанка; ``False`` — пропущено как устаревшее."""
        stored = await self._stored_payload(write.point_id)
        if stored is None:
            # Точки ещё нет — создаём целиком (первая индексация чанка).
            await self._guard(
                self._client.upsert(
                    collection_name=self._collection,
                    points=[self._to_point(write)],
                )
            )
            return True
        version = stored.get("content_version")
        if version is not None and int(version) >= write.content_version:
            return False
        await self._merge(write)
        return True

    async def _merge(self, write: ChunkWrite) -> None:
        """Дописывает векторы и знаки, сохраняя остальной payload (§9.4).

        ``upsert`` заменил бы payload целиком и снёс коммерческие поля
        (цена/остаток/маржа), которые пишет синхронный путь.
        """
        vectors = self._named_vectors(write)
        if vectors:
            await self._guard(
                self._client.update_vectors(
                    collection_name=self._collection,
                    points=[
                        models.PointVectors(
                            id=write.point_id, vector=vectors
                        )
                    ],
                )
            )
        await self._guard(
            self._client.set_payload(
                collection_name=self._collection,
                payload=self._payload(write),
                points=[write.point_id],
            )
        )

    async def _stored_payload(self, point_id: str) -> dict | None:
        """Payload точки или ``None``, если точки нет в коллекции."""
        records = await self._guard(
            self._client.retrieve(
                collection_name=self._collection,
                ids=[point_id],
                with_payload=["content_version"],
                with_vectors=False,
            )
        )
        if not records:
            return None
        return records[0].payload or {}

    @classmethod
    def _to_point(cls, write: ChunkWrite) -> models.PointStruct:
        return models.PointStruct(
            id=write.point_id,
            vector=cls._named_vectors(write),
            payload=cls._payload(write),
        )

    @staticmethod
    def _named_vectors(write: ChunkWrite) -> dict[str, object]:
        vectors: dict[str, object] = {}
        if write.dense is not None:
            vectors[DENSE_VECTOR] = list(write.dense)
        if write.sparse is not None:
            vectors[SPARSE_VECTOR] = models.SparseVector(
                indices=list(write.sparse.indices),
                values=list(write.sparse.values),
            )
        return vectors

    @staticmethod
    def _payload(write: ChunkWrite) -> dict[str, object]:
        payload: dict[str, object] = {
            "product_id": str(write.product_id),
            "sku": write.sku,
            "chunk_ix": write.chunk_ix,
            "aggregate_version": write.aggregate_version,
            "content_version": write.content_version,
            "model_version": write.model_version,
            "indexed_at": datetime.now(UTC).isoformat(),
        }
        if write.token_count is not None:
            payload["token_count"] = write.token_count
        return payload

    @staticmethod
    async def _guard(awaitable):
        try:
            return await awaitable
        except _QDRANT_ERRORS as exc:
            raise VectorIndexError(str(exc)) from exc
