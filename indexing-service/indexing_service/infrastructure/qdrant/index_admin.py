"""Адаптер ``QdrantIndexAdmin`` — реализация порта ``VectorIndexAdmin``."""

from qdrant_client import AsyncQdrantClient

from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.collection_spec import (
    epoch_ready_filter,
)
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)


class QdrantIndexAdmin:
    """Управляет коллекциями и алиасом Qdrant для reindex (§8.2)."""

    def __init__(self, client: AsyncQdrantClient, *, dim: int) -> None:
        self._client = client
        self._dim = dim

    async def provision(self, collection: str) -> None:
        await CollectionProvisioner(
            self._client, collection=collection, dim=self._dim
        ).ensure()

    async def swap_alias(self, alias: str, to_collection: str) -> None:
        await CollectionProvisioner(
            self._client, collection=to_collection, dim=self._dim
        ).point_alias(alias)

    def writer(self, collection: str) -> VectorIndex:
        return QdrantVectorIndex(self._client, collection=collection)

    async def count_ready_roots(
        self,
        collection: str,
        *,
        epoch: str,
        expected_model: str | None = None,
    ) -> int:
        """Считает готовые корневые точки эпохи в коллекции (Q6).

        Args:
            collection: Коллекция эпохи.
            epoch: Метка эпохи в payload (== имя целевой коллекции).
            expected_model: Закреплённая модель или ``None`` — тогда
                достаточно любого непустого водяного знака модели.

        Returns:
            Число товаров, у которых векторы эпохи реально записаны.
        """
        result = await self._client.count(
            collection_name=collection,
            count_filter=epoch_ready_filter(
                epoch=epoch, expected_model=expected_model
            ),
            exact=True,
        )
        return int(result.count)
