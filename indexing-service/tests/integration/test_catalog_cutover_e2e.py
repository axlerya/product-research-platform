"""Integration: горячий путь каталога после cutover (шаг 5, §6, §9).

Событие каталога → карточка товара в Qdrant (без векторов) + job и команда
в Postgres. Проверяем на настоящих Qdrant и Postgres то, чего фейки не
покажут: что точка реально создаётся без векторов и что водяные знаки
текста/модели на неё не ставятся раньше времени.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from indexing_service.application.dto.events import ProductCreatedEvent
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.use_cases.process_catalog_event import (
    ProcessCatalogEvent,
)
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.change_classifier import IndexingAction
from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)
from tests.support.fakes import FakeCatalogGateway, FixedClock

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)


def _snapshot(product_id, version: int = 1) -> ProductSnapshot:
    return ProductSnapshot(
        product_id=product_id,
        sku="PROD-001",
        name="Наушники",
        description="Беспроводные",
        category="Электроника",
        brand="AudioMax",
        supplier="TechSupply",
        price=Decimal("129.99"),
        cost=Decimal("65.00"),
        currency="RUB",
        stock=245,
        sales_per_month=87,
        avg_rating=Decimal("4.5"),
        review_count=1243,
        source_updated_at=date(2024, 3, 15),
        aggregate_version=version,
    )


async def _use_case(qdrant_client, sessionmaker_, collection: str):
    await CollectionProvisioner(
        qdrant_client, collection=collection, dim=4
    ).ensure()
    clock = FixedClock(_NOW)
    return ProcessCatalogEvent(
        index=QdrantVectorIndex(qdrant_client, collection=collection),
        request_embedding=RequestEmbedding(
            SqlAlchemyUnitOfWork(sessionmaker_),
            clock,
            chunker=SingleDocument(),
            expected_model=None,
            max_texts=32,
        ),
        catalog=FakeCatalogGateway([]),
        clock=clock,
    )


async def _count(sessionmaker_, table: str) -> int:
    async with sessionmaker_() as session:
        return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def test_created_event_produces_card_and_job(
    qdrant_client, sessionmaker_
):
    collection = f"cutover_it_{uuid4().hex[:8]}"
    use_case = await _use_case(qdrant_client, sessionmaker_, collection)
    product_id = uuid4()
    event = ProductCreatedEvent(
        event_id=uuid4(),
        occurred_at=_NOW,
        product=_snapshot(product_id),
    )

    action = await use_case.handle(event)

    assert action is IndexingAction.FULL_INDEX
    records = await qdrant_client.retrieve(
        collection_name=collection,
        ids=[str(product_id)],
        with_payload=True,
        with_vectors=True,
    )
    assert len(records) == 1, "карточка товара должна появиться сразу"
    payload = records[0].payload
    assert payload["price"] == 129.99
    assert payload["sku"] == "PROD-001"
    assert payload["aggregate_version"] == 1
    # векторов ещё нет — их посчитает embedding-service
    assert not records[0].vector
    # и текст не объявлен проиндексированным
    assert "content_hash" not in payload
    assert "model_version" not in payload

    assert await _count(sessionmaker_, "indexing_jobs") == 1
    assert await _count(sessionmaker_, "embedding_requests") == 1
    assert await _count(sessionmaker_, "outbox") == 1


async def test_redelivered_created_event_is_idempotent(
    qdrant_client, sessionmaker_
):
    collection = f"cutover_it_{uuid4().hex[:8]}"
    use_case = await _use_case(qdrant_client, sessionmaker_, collection)
    event = ProductCreatedEvent(
        event_id=uuid4(), occurred_at=_NOW, product=_snapshot(uuid4())
    )

    await use_case.handle(event)
    await use_case.handle(event)

    assert await _count(sessionmaker_, "indexing_jobs") == 1
    assert await _count(sessionmaker_, "outbox") == 1
