"""Адаптер ``QdrantEmbeddingSink`` — реализация порта ``EmbeddingResultSink``.

Пишет точку чанка (ключ — ``point_id``) с двумя водяными знаками
(``aggregate_version`` + ``content_version``, §9.4). Guard по
``content_version``: результат старее уже записанного — пропускаем (не
затираем свежий текст). Инфраструктурные сбои → ``VectorIndexError`` (ретрай).
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
        stored = await self._stored_content_version(write.point_id)
        if stored is not None and stored >= write.content_version:
            return False
        await self._guard(
            self._client.upsert(
                collection_name=self._collection,
                points=[self._to_point(write)],
            )
        )
        return True

    async def _stored_content_version(self, point_id: str) -> int | None:
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
        value = (records[0].payload or {}).get("content_version")
        return int(value) if value is not None else None

    @staticmethod
    def _to_point(write: ChunkWrite) -> models.PointStruct:
        vectors: dict[str, object] = {}
        if write.dense is not None:
            vectors[DENSE_VECTOR] = list(write.dense)
        if write.sparse is not None:
            vectors[SPARSE_VECTOR] = models.SparseVector(
                indices=list(write.sparse.indices),
                values=list(write.sparse.values),
            )
        payload: dict[str, object] = {
            "product_id": str(write.product_id),
            "sku": write.sku,
            "chunk_ix": write.chunk_ix,
            "aggregate_version": write.aggregate_version,
            "content_version": write.content_version,
            # Водяные знаки текста и модели ставит только тот, кто посчитал
            # векторы: до этого момента текст не проиндексирован (§9.4).
            "content_hash": write.content_hash,
            "model_version": write.model_version,
            "indexed_at": datetime.now(UTC).isoformat(),
        }
        if write.token_count is not None:
            payload["token_count"] = write.token_count
        return models.PointStruct(
            id=write.point_id, vector=vectors, payload=payload
        )

    @staticmethod
    async def _guard(awaitable):
        try:
            return await awaitable
        except _QDRANT_ERRORS as exc:
            raise VectorIndexError(str(exc)) from exc
