"""Integration: фаза A против реального Postgres (§9.1, §9.2).

Проверяем то, что фейки проверить не могут: job, команды и строки outbox
ложатся ОДНОЙ транзакцией, а редоставка события каталога не спотыкается о
уникальность ``(product_id, content_version)``.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from indexing_service.application.dto.embedding_job import EmbeddingJobRequest
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.chunking import RecursiveChunker
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import IndexAction
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
_TEXT = "Товар: Кружка. Бренд: Acme. Категория: Посуда. Описание: белая"


class _Clock:
    def now(self):
        return _NOW


def _request(product_id: ProductId, *, content_version: int = 1):
    return EmbeddingJobRequest(
        product_id=product_id,
        sku=Sku("PROD-1"),
        aggregate_version=content_version,
        content_version=content_version,
        content_hash=ContentHash.of(_TEXT),
        text=SearchText(_TEXT),
        action=IndexAction.FULL_INDEX,
    )


def _use_case(sessionmaker_, *, max_chars: int = 1000, max_texts: int = 32):
    return RequestEmbedding(
        SqlAlchemyUnitOfWork(sessionmaker_),
        _Clock(),
        chunker=RecursiveChunker(max_chars=max_chars),
        expected_model=None,
        max_texts=max_texts,
    )


async def _count(sessionmaker_, table: str) -> int:
    async with sessionmaker_() as session:
        return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def test_job_command_and_outbox_land_together(sessionmaker_):
    product_id = ProductId(uuid4())

    assert await _use_case(sessionmaker_).handle(_request(product_id)) is True

    assert await _count(sessionmaker_, "indexing_jobs") == 1
    assert await _count(sessionmaker_, "embedding_requests") == 1
    assert await _count(sessionmaker_, "outbox") == 1


async def test_redelivery_does_not_duplicate_job(sessionmaker_):
    product_id = ProductId(uuid4())
    use_case = _use_case(sessionmaker_)

    assert await use_case.handle(_request(product_id)) is True
    assert await use_case.handle(_request(product_id)) is False

    assert await _count(sessionmaker_, "indexing_jobs") == 1
    assert await _count(sessionmaker_, "outbox") == 1


async def test_batches_produce_one_outbox_row_each(sessionmaker_):
    product_id = ProductId(uuid4())

    await _use_case(sessionmaker_, max_chars=12, max_texts=2).handle(
        _request(product_id)
    )

    async with sessionmaker_() as session:
        chunks = await session.scalar(
            text("SELECT jsonb_array_length(chunks) FROM indexing_jobs")
        )
    expected = -(-chunks // 2)  # ceil
    assert await _count(sessionmaker_, "embedding_requests") == expected
    assert await _count(sessionmaker_, "outbox") == expected
