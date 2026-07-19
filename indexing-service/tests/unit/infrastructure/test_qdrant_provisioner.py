"""Тесты ``CollectionProvisioner`` на фейковом клиенте (без Docker)."""

from types import SimpleNamespace

from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.collection_spec import (
    DENSE_VECTOR,
    PAYLOAD_INDEXES,
    SPARSE_VECTOR,
)


class FakeClient:
    def __init__(self, *, exists=False, aliases=()) -> None:
        self.calls: list[tuple] = []
        self._exists = exists
        self._aliases = list(aliases)

    async def collection_exists(self, name):
        return self._exists

    async def create_collection(self, **kw):
        self.calls.append(("create", kw))

    async def create_payload_index(
        self, collection_name, *, field_name, field_schema
    ):
        self.calls.append(("index", field_name))

    async def get_aliases(self):
        aliases = [SimpleNamespace(alias_name=a) for a in self._aliases]
        return SimpleNamespace(aliases=aliases)

    async def update_collection_aliases(self, *, change_aliases_operations):
        self.calls.append(("aliases", change_aliases_operations))


def _provisioner(client, collection="products_v1"):
    return CollectionProvisioner(client, collection=collection, dim=1024)


async def test_ensure_creates_when_absent():
    client = FakeClient(exists=False)
    await _provisioner(client).ensure()
    assert client.calls[0][0] == "create"
    create_kw = client.calls[0][1]
    assert create_kw["vectors_config"][DENSE_VECTOR].size == 1024
    assert SPARSE_VECTOR in create_kw["sparse_vectors_config"]
    index_fields = [c[1] for c in client.calls if c[0] == "index"]
    assert len(index_fields) == len(PAYLOAD_INDEXES)


async def test_ensure_noop_when_exists():
    client = FakeClient(exists=True)
    await _provisioner(client).ensure()
    assert client.calls == []


async def test_point_alias_create_only_first_time():
    client = FakeClient(aliases=())
    await _provisioner(client).point_alias("products")
    op, operations = client.calls[0]
    assert op == "aliases"
    assert len(operations) == 1


async def test_point_alias_swaps_when_exists():
    client = FakeClient(aliases=("products",))
    await _provisioner(client, "products_v2").point_alias("products")
    _, operations = client.calls[0]
    assert len(operations) == 2
