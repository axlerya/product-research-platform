"""Провижининг Qdrant: idempotent create, payload-индексы, alias (§4.3)."""

from qdrant_client import AsyncQdrantClient, models

from indexing_service.infrastructure.qdrant.collection_spec import (
    PAYLOAD_INDEXES,
    sparse_vectors_config,
    vectors_config,
)


class CollectionProvisioner:
    """Создаёт коллекцию и управляет алиасом чтения."""

    def __init__(
        self, client: AsyncQdrantClient, *, collection: str, dim: int
    ) -> None:
        self._client = client
        self._collection = collection
        self._dim = dim

    async def ensure(self) -> None:
        """Idempotent: создаёт коллекцию + индексы, если её ещё нет."""
        if await self._client.collection_exists(self._collection):
            return
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=vectors_config(self._dim),
            sparse_vectors_config=sparse_vectors_config(),
        )
        for field, schema in PAYLOAD_INDEXES:
            await self._client.create_payload_index(
                self._collection, field_name=field, field_schema=schema
            )

    async def point_alias(self, alias: str) -> None:
        """Атомарно направляет ``alias`` на текущую коллекцию (§8.2)."""
        operations = []
        existing = await self._client.get_aliases()
        if any(item.alias_name == alias for item in existing.aliases):
            operations.append(
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=alias)
                )
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=self._collection, alias_name=alias
                )
            )
        )
        await self._client.update_collection_aliases(
            change_aliases_operations=operations
        )
