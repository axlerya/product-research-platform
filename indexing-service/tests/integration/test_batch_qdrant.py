"""Integration: reindex/reconcile против реального Qdrant и Postgres.

После перехода на job-модель batch-операции векторы не считают: они пишут
карточки товаров и заводят задания. Поэтому проверяем именно это — точки
в нужной коллекции без векторов и строки заданий в БД.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.use_cases.reconcile_catalog import (
    ReconcileCatalog,
)
from indexing_service.application.use_cases.reindex_catalog import (
    ReindexCatalog,
)
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from indexing_service.infrastructure.qdrant.collection_provisioner import (
    CollectionProvisioner,
)
from indexing_service.infrastructure.qdrant.index_admin import QdrantIndexAdmin
from indexing_service.infrastructure.qdrant.vector_index import (
    QdrantVectorIndex,
)
from indexing_service.infrastructure.services.clock import SystemClock
from tests.support.fakes import FakeCatalogGateway

pytestmark = pytest.mark.integration

_DIM = 8


def _snap(seq: int, version: int = 1) -> ProductSnapshot:
    return ProductSnapshot(
        product_id=UUID(int=seq),
        sku=f"PROD-{seq:03d}",
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


def _request_embedding(sessionmaker_):
    return RequestEmbedding(
        SqlAlchemyUnitOfWork(sessionmaker_),
        SystemClock(),
        chunker=SingleDocument(),
        expected_model=None,
        max_texts=32,
    )


async def _scalar(sessionmaker_, sql: str, **params) -> int:
    async with sessionmaker_() as session:
        return await session.scalar(text(sql), params or None)


async def _finish_epoch(sessionmaker_, target: str) -> None:
    """Помечает все задания эпохи завершёнными (эмуляция плеча B)."""
    async with sessionmaker_() as session:
        await session.execute(
            text(
                "UPDATE indexing_jobs SET status = 'done' "
                "WHERE target_collection = :target"
            ),
            {"target": target},
        )
        await session.commit()


async def test_reindex_fills_target_and_queues_epoch(
    qdrant_client, sessionmaker_
):
    alias = f"alias_{uuid4().hex[:8]}"
    target = f"products_{uuid4().hex[:8]}"
    reindex = ReindexCatalog(
        admin=QdrantIndexAdmin(qdrant_client, dim=_DIM),
        request_embedding=_request_embedding(sessionmaker_),
        uow=SqlAlchemyUnitOfWork(sessionmaker_),
        catalog=FakeCatalogGateway([_snap(1), _snap(2)]),
        clock=SystemClock(),
    )

    report = await reindex.execute(target_collection=target)

    assert report.queued == 2
    # карточки легли в НОВУЮ коллекцию, alias ещё не переключён
    count = await qdrant_client.count(collection_name=target)
    assert count.count == 2
    jobs = await _scalar(
        sessionmaker_,
        "SELECT count(*) FROM indexing_jobs "
        "WHERE target_collection = :target",
        target=target,
    )
    assert jobs == 2

    # эпоха не готова → свап не происходит
    swap = await reindex.swap(target_collection=target, alias=alias)
    assert swap.swapped is False
    assert swap.pending == 2

    await _finish_epoch(sessionmaker_, target)
    swap = await reindex.swap(target_collection=target, alias=alias)
    assert swap.swapped is True
    aliased = await qdrant_client.count(collection_name=alias)
    assert aliased.count == 2


async def test_reconcile_queues_missing_and_tombstones_orphan(
    qdrant_client, sessionmaker_
):
    collection = f"products_{uuid4().hex[:8]}"
    await CollectionProvisioner(
        qdrant_client, collection=collection, dim=_DIM
    ).ensure()
    index = QdrantVectorIndex(qdrant_client, collection=collection)
    clock = SystemClock()

    # Предзаливаем товар A (станет orphan), каталог знает только товар B.
    await index.upsert_payload(
        ProductId(UUID(int=1)),
        {"aggregate_version": 1, "is_deleted": False, "sku": "PROD-001"},
    )
    report = await ReconcileCatalog(
        index=index,
        request_embedding=_request_embedding(sessionmaker_),
        catalog=FakeCatalogGateway([_snap(2)]),
        clock=clock,
    ).execute()

    assert report.indexed == 1  # B добавлен и поставлен в очередь
    assert report.tombstoned == 1  # A осиротел

    orphan = await qdrant_client.retrieve(
        collection_name=collection, ids=[str(UUID(int=1))], with_payload=True
    )
    assert orphan[0].payload["is_deleted"] is True
    fresh = await qdrant_client.retrieve(
        collection_name=collection, ids=[str(UUID(int=2))], with_payload=True
    )
    assert fresh[0].payload["is_deleted"] is False
    assert await _scalar(sessionmaker_, "SELECT count(*) FROM outbox") == 1
