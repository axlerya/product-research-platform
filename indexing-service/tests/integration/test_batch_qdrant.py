"""Integration: reindex/reconcile против реального Qdrant."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.indexer import index_snapshot
from indexing_service.application.use_cases.reconcile_catalog import (
    ReconcileCatalog,
)
from indexing_service.application.use_cases.reindex_catalog import (
    ReindexCatalog,
)
from indexing_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingModel,
)
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


async def test_reindex_backfills_and_swaps_alias(qdrant_client):
    alias = f"alias_{uuid4().hex[:8]}"
    target = f"products_{uuid4().hex[:8]}"
    report = await ReindexCatalog(
        admin=QdrantIndexAdmin(qdrant_client, dim=_DIM),
        embedder=DeterministicEmbeddingModel(dim=_DIM),
        catalog=FakeCatalogGateway([_snap(1), _snap(2)]),
        clock=SystemClock(),
    ).execute(target_collection=target, alias=alias)

    assert report.indexed == 2
    count = await qdrant_client.count(collection_name=alias)
    assert count.count == 2


async def test_reconcile_indexes_missing_and_tombstones_orphan(qdrant_client):
    collection = f"products_{uuid4().hex[:8]}"
    await CollectionProvisioner(
        qdrant_client, collection=collection, dim=_DIM
    ).ensure()
    index = QdrantVectorIndex(qdrant_client, collection=collection)
    embedder = DeterministicEmbeddingModel(dim=_DIM)
    clock = SystemClock()

    # Предзаливаем товар A (станет orphan), каталог знает только товар B.
    await index_snapshot(_snap(1), index=index, embedder=embedder, clock=clock)
    report = await ReconcileCatalog(
        index=index,
        embedder=embedder,
        catalog=FakeCatalogGateway([_snap(2)]),
        clock=clock,
    ).execute()

    assert report.indexed == 1  # B добавлен
    assert report.tombstoned == 1  # A осиротел

    orphan = await qdrant_client.retrieve(
        collection_name=collection, ids=[str(UUID(int=1))], with_payload=True
    )
    assert orphan[0].payload["is_deleted"] is True
    fresh = await qdrant_client.retrieve(
        collection_name=collection, ids=[str(UUID(int=2))], with_payload=True
    )
    assert fresh[0].payload["is_deleted"] is False
