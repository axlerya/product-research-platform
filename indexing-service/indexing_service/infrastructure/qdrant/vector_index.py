"""Адаптер ``QdrantVectorIndex`` — реализация порта ``VectorIndex``.

Инфраструктурные сбои Qdrant/сети переводит в ``VectorIndexError``
(временная ошибка → ретрай, §7.1).

Адресация точек товара (§9.4): у товара одна корневая точка (id == UUID
товара) и, после rechunk, дополнительные чанк-точки. Чтение водяного знака
и создание карточки работают с корневой точкой, а ``set_payload`` — со
**всеми** точками товара: цена, наличие и tombstone обязаны быть
одинаковыми на всех его векторах. Скан сверки отдаёт только корневые точки:
чанк — не самостоятельный товар.
"""

from collections.abc import AsyncIterator, Mapping
from uuid import UUID

import httpx
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)

from indexing_service.application.dto.point import PointRecord, WatermarkEntry
from indexing_service.application.exceptions import VectorIndexError
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.watermark import IndexingWatermark
from indexing_service.infrastructure.qdrant.collection_spec import (
    product_points_filter,
    root_points_filter,
)
from indexing_service.infrastructure.qdrant.mappers import (
    point_id,
    to_named_vectors,
    to_point_struct,
    watermark_from_payload,
)

_QDRANT_ERRORS = (
    UnexpectedResponse,
    ResponseHandlingException,
    httpx.HTTPError,
    OSError,
)


class QdrantVectorIndex:
    """Пишет/читает точки в коллекцию (обычно через alias)."""

    def __init__(
        self, client: AsyncQdrantClient, *, collection: str
    ) -> None:
        self._client = client
        self._collection = collection

    async def get_watermark(
        self, product_id: ProductId
    ) -> IndexingWatermark | None:
        records = await self._guard(
            self._client.retrieve(
                collection_name=self._collection,
                ids=[point_id(product_id)],
                with_payload=True,
                with_vectors=False,
            )
        )
        if not records:
            return None
        return watermark_from_payload(records[0].payload)

    async def scroll_watermarks(self) -> AsyncIterator[WatermarkEntry]:
        offset = None
        while True:
            records, offset = await self._guard(
                self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=root_points_filter(),
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
            )
            for record in records:
                watermark = watermark_from_payload(record.payload)
                if watermark is None:
                    continue
                payload = record.payload or {}
                yield WatermarkEntry(
                    product_id=ProductId(UUID(str(record.id))),
                    watermark=watermark,
                    is_deleted=bool(payload.get("is_deleted", False)),
                )
            if offset is None:
                break

    async def upsert_document(self, point: PointRecord) -> None:
        await self._guard(
            self._client.upsert(
                collection_name=self._collection,
                points=[to_point_struct(point)],
            )
        )

    async def upsert_payload(
        self, product_id: ProductId, fields: Mapping[str, object]
    ) -> None:
        await self._guard(
            self._client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=point_id(product_id),
                        vector={},  # векторы допишет async-результат
                        payload=dict(fields),
                    )
                ],
            )
        )

    async def update_vectors(
        self, product_id: ProductId, embedding: Embedding
    ) -> None:
        await self._guard(
            self._client.update_vectors(
                collection_name=self._collection,
                points=[
                    models.PointVectors(
                        id=point_id(product_id),
                        vector=to_named_vectors(embedding),
                    )
                ],
            )
        )

    async def set_payload(
        self, product_id: ProductId, fields: Mapping[str, object]
    ) -> None:
        # Фильтром по товару, а не списком id: у товара может быть несколько
        # точек, и коммерческие поля с tombstone обязаны накрыть все.
        await self._guard(
            self._client.set_payload(
                collection_name=self._collection,
                payload=dict(fields),
                points=product_points_filter(str(product_id.value)),
            )
        )

    @staticmethod
    async def _guard(awaitable):
        try:
            return await awaitable
        except _QDRANT_ERRORS as exc:
            raise VectorIndexError(str(exc)) from exc
