"""Тесты ``QdrantIndexAdmin`` на фейковом клиенте (без Docker)."""

from types import SimpleNamespace

from indexing_service.infrastructure.qdrant.index_admin import QdrantIndexAdmin
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)


class FakeClient:
    def __init__(self, *, aliases=(), count=0) -> None:
        self.calls: list[tuple] = []
        self._aliases = list(aliases)
        self._count = count

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

    async def count(self, **kw):
        self.calls.append(("count", kw))
        return SimpleNamespace(count=self._count)


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


async def test_provision_indexes_reindex_epoch():
    """Гейт свапа фильтрует по эпохе — поле обязано быть проиндексировано."""
    client = FakeClient()
    await QdrantIndexAdmin(client, dim=1024).provision("products_v2")
    indexed = [name for op, name in client.calls if op == "index"]
    assert "reindex_epoch" in indexed


async def test_count_ready_roots_counts_only_finished_root_points():
    """Считаем корневые точки эпохи, у которых реально есть векторы."""
    client = FakeClient(count=7)

    total = await QdrantIndexAdmin(client, dim=1024).count_ready_roots(
        "products_v2", epoch="products_v2", expected_model="bge-m3@x"
    )

    assert total == 7
    _, kw = next(call for call in client.calls if call[0] == "count")
    assert kw["collection_name"] == "products_v2"
    assert kw["exact"] is True
    keys = {c.key: c for c in kw["count_filter"].must}
    assert keys["reindex_epoch"].match.value == "products_v2"
    assert keys["model_version"].match.value == "bge-m3@x"
    # чанки не считаем — иначе один многочанковый товар пройдёт гейт за всех
    excluded = kw["count_filter"].must_not
    assert any(
        getattr(c, "key", None) == "chunk_ix" and c.range.gt == 0
        for c in excluded
    )
    # удалённые и точки без версии текста тоже не в счёт
    assert any(
        getattr(c, "key", None) == "is_deleted" and c.match.value is True
        for c in excluded
    )
    assert any(
        getattr(getattr(c, "is_empty", None), "key", None) == "content_version"
        for c in excluded
    )


async def test_count_ready_roots_without_pinned_model_requires_watermark():
    """Модель не закреплена → достаточно непустого ``model_version``."""
    client = FakeClient(count=1)

    await QdrantIndexAdmin(client, dim=1024).count_ready_roots(
        "products_v2", epoch="products_v2", expected_model=None
    )

    _, kw = next(call for call in client.calls if call[0] == "count")
    assert all(c.key != "model_version" for c in kw["count_filter"].must)
    assert any(
        getattr(getattr(c, "is_empty", None), "key", None) == "model_version"
        for c in kw["count_filter"].must_not
    )
