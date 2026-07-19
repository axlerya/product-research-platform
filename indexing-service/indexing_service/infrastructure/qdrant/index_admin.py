"""Адаптер ``QdrantIndexAdmin`` — реализация порта ``VectorIndexAdmin``."""

from qdrant_client import AsyncQdrantClient

from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
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
