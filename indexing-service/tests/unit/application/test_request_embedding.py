"""Тесты use case ``RequestEmbedding`` — фаза A конвейера (§6, §9)."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

import pytest

from indexing_service.application.dto.embedding_job import EmbeddingJobRequest
from indexing_service.application.embedding_command import EVENT_TYPE
from indexing_service.application.request_id import deterministic_request_id
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.chunking import (
    RecursiveChunker,
    SingleDocument,
)
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import (
    ChunkStatus,
    IndexAction,
    JobStatus,
    RequestStatus,
)
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.domain.value_objects.sku import Sku

_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
_PRODUCT = ProductId(UUID(int=42))
_TEXT = "Товар: Кружка\nБренд: Acme\nКатегория: Посуда\nОписание: белая"


class _FakeJobs:
    def __init__(self) -> None:
        self.store: dict = {}
        self.by_product: dict[tuple, object] = {}

    async def upsert(self, job) -> None:
        self.store[job.job_id] = job
        key = (job.product_id, job.content_version, job.target_collection)
        self.by_product[key] = job

    async def get(self, job_id):
        return self.store.get(job_id)

    async def get_by_product(
        self, product_id, content_version, target_collection=None
    ):
        return self.by_product.get(
            (product_id, content_version, target_collection)
        )


class _FakeRequests:
    def __init__(self) -> None:
        self.store: dict = {}

    async def add(self, request) -> None:
        self.store[request.request_id] = request

    async def get(self, request_id):
        return self.store.get(request_id)

    async def update(self, request) -> None:
        self.store[request.request_id] = request


class _FakeOutbox:
    def __init__(self) -> None:
        self.messages: list = []

    async def add_many(self, messages) -> None:
        self.messages.extend(messages)


class _FakeUoW:
    def __init__(self) -> None:
        self.jobs = _FakeJobs()
        self.requests = _FakeRequests()
        self.outbox = _FakeOutbox()
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


class _Clock:
    def now(self):
        return _NOW


def _request(*, text: str = _TEXT, content_version: int = 3, **over):
    fields = dict(
        product_id=_PRODUCT,
        sku=Sku("PROD-1"),
        aggregate_version=3,
        content_version=content_version,
        content_hash=ContentHash.of(text),
        text=SearchText(text),
        action=IndexAction.FULL_INDEX,
    )
    fields.update(over)
    return EmbeddingJobRequest(**fields)


def _use_case(uow, *, chunker=None, max_texts=32, expected_model=None):
    return RequestEmbedding(
        uow,
        _Clock(),
        chunker=chunker or SingleDocument(),
        expected_model=expected_model,
        max_texts=max_texts,
    )


async def test_creates_job_and_command_in_one_transaction():
    uow = _FakeUoW()

    assert await _use_case(uow).handle(_request()) is True

    assert uow.commits == 1
    [job] = list(uow.jobs.store.values())
    assert job.status is JobStatus.PENDING
    assert job.product_id == _PRODUCT
    assert job.content_version == 3
    assert job.content_hash == ContentHash.of(_TEXT)
    assert [c.status for c in job.chunks] == [ChunkStatus.PENDING]
    [command] = list(uow.requests.store.values())
    assert command.job_id == job.job_id
    assert command.attempt == 0
    assert command.status is RequestStatus.PENDING
    assert command.items[0].text == _TEXT
    assert len(uow.outbox.messages) == 1
    assert uow.outbox.messages[0].event_type == EVENT_TYPE


async def test_zero_chunk_points_at_the_product_itself():
    """Векторы домержатся к точке товара, а не в отдельную сироту (§9.4)."""
    uow = _FakeUoW()
    await _use_case(uow).handle(_request())

    [job] = list(uow.jobs.store.values())
    assert job.chunks[0].point_id == str(_PRODUCT.value)
    assert job.chunks[0].text_id == job.chunks[0].point_id


async def test_redelivery_of_same_content_version_is_noop():
    uow = _FakeUoW()
    use_case = _use_case(uow)

    assert await use_case.handle(_request()) is True
    assert await use_case.handle(_request()) is False

    assert len(uow.jobs.store) == 1
    assert len(uow.requests.store) == 1
    assert len(uow.outbox.messages) == 1


async def test_new_content_version_creates_another_job():
    uow = _FakeUoW()
    use_case = _use_case(uow)

    await use_case.handle(_request(content_version=3))
    assert await use_case.handle(_request(content_version=4)) is True

    assert len(uow.jobs.store) == 2


async def test_chunked_text_becomes_several_points():
    uow = _FakeUoW()
    chunker = RecursiveChunker(max_chars=20)

    await _use_case(uow, chunker=chunker).handle(_request())

    [job] = list(uow.jobs.store.values())
    assert len(job.chunks) > 1
    assert [c.chunk_ix for c in job.chunks] == list(range(len(job.chunks)))
    # точки уникальны, нулевая — точка товара
    assert len({c.point_id for c in job.chunks}) == len(job.chunks)
    assert job.chunks[0].point_id == str(_PRODUCT.value)


async def test_items_are_split_into_commands_by_max_texts():
    uow = _FakeUoW()
    chunker = RecursiveChunker(max_chars=12)

    await _use_case(uow, chunker=chunker, max_texts=2).handle(_request())

    [job] = list(uow.jobs.store.values())
    commands = list(uow.requests.store.values())
    assert len(commands) == -(-len(job.chunks) // 2)  # ceil
    assert all(len(command.items) <= 2 for command in commands)
    # каждой команде — своя строка outbox
    assert len(uow.outbox.messages) == len(commands)
    # вместе команды покрывают все чанки ровно один раз
    covered = [item.text_id for c in commands for item in c.items]
    assert covered == [chunk.text_id for chunk in job.chunks]


async def test_expected_model_reaches_job_and_command():
    uow = _FakeUoW()

    await _use_case(uow, expected_model="BAAI/bge-m3").handle(_request())

    [job] = list(uow.jobs.store.values())
    assert job.expected_model == "BAAI/bge-m3"
    assert uow.outbox.messages[0].payload["data"]["model"] == "BAAI/bge-m3"


async def test_model_is_omitted_when_not_pinned():
    uow = _FakeUoW()
    await _use_case(uow).handle(_request())
    assert "model" not in uow.outbox.messages[0].payload["data"]


async def test_request_id_is_derived_from_job_and_items():
    """id команды выводится детерминированно, а не случайно (§9.1)."""
    uow = _FakeUoW()
    await _use_case(uow).handle(_request())

    [job] = list(uow.jobs.store.values())
    [command] = list(uow.requests.store.values())
    assert command.request_id == deterministic_request_id(
        job.job_id, 0, command.items
    )
    # message_id конверта тоже выводится из id команды, а не случаен
    assert uow.outbox.messages[0].id == uuid5(
        command.request_id.value, "outbox"
    )


async def test_reindex_job_is_not_deduped_against_live_job():
    """Эпоха reindex — отдельный ключ, иначе не встало бы ни одно задание."""
    uow = _FakeUoW()
    use_case = _use_case(uow)

    assert await use_case.handle(_request()) is True
    assert (
        await use_case.handle(_request(target_collection="products_v2"))
        is True
    )

    assert len(uow.jobs.store) == 2
    targets = {job.target_collection for job in uow.jobs.store.values()}
    assert targets == {None, "products_v2"}


async def test_target_collection_is_carried_for_reindex():
    uow = _FakeUoW()
    await _use_case(uow).handle(
        _request(action=IndexAction.REEMBED, target_collection="products_v2")
    )
    [job] = list(uow.jobs.store.values())
    assert job.target_collection == "products_v2"
    assert job.action is IndexAction.REEMBED


async def test_rejects_non_positive_max_texts():
    with pytest.raises(ValueError):
        _use_case(_FakeUoW(), max_texts=0)
