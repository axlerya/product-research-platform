"""Тесты ``QdrantIndexAdmin`` на фейковом клиенте (без Docker)."""

from types import SimpleNamespace

from indexing_service.infrastructure.qdrant.index_admin import QdrantIndexAdmin
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)


class FakeClient:
    def __init__(self, *, aliases=()) -> None:
        self.calls: list[tuple] = []
        self._aliases = list(aliases)

    async def collection_exists(self, name):
        return False

    async def create_collection(self, **kw):
        self.calls.append(("create", kw))

    async def create_payload_index(self, collection_name, **kw):
        self.calls.append(("index", kw["field_name"]))

    async def get_aliases(self):
        aliases = [SimpleNamespace(alias_name=a) for a in self._aliases]
        return SimpleNamespace(aliases=aliases)

    async def update_collection_aliases(self, *, change_aliases_operations):
        self.calls.append(("aliases", change_aliases_operations))


async def test_provision_creates_collection():
    client = FakeClient()
    await QdrantIndexAdmin(client, dim=1024).provision("products_v2")
    assert client.calls[0][0] == "create"


async def test_swap_alias_updates_aliases():
    client = FakeClient(aliases=("products",))
    await QdrantIndexAdmin(client, dim=1024).swap_alias(
        "products", "products_v2"
    )
    assert any(call[0] == "aliases" for call in client.calls)


def test_writer_returns_vector_index():
    writer = QdrantIndexAdmin(FakeClient(), dim=1024).writer("products_v2")
    assert isinstance(writer, QdrantVectorIndex)
