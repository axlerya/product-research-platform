"""Разделяемые операции индексации (consumer + batch use cases).

Держит единую логику «снимок → документ → эмбеддинг → upsert» и tombstone,
чтобы consumer, reindex и reconcile не дублировали её.
"""

from indexing_service.application.document_builder import to_product_document
from indexing_service.application.dto.point import PointRecord
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.payload import full_payload, tombstone_fields
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.embedding_model import EmbeddingModel
from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.domain.value_objects.identifiers import ProductId


async def index_snapshot(
    snapshot: ProductSnapshot,
    *,
    index: VectorIndex,
    embedder: EmbeddingModel,
    clock: Clock,
) -> None:
    """Полная индексация снимка: документ → эмбеддинг → upsert."""
    document = to_product_document(snapshot)
    [embedding] = await embedder.embed_documents([document.search_text()])
    payload = full_payload(
        document,
        model_version=embedding.model_id.key,
        indexed_at=clock.now(),
    )
    await index.upsert_document(
        PointRecord(
            product_id=document.product_id,
            embedding=embedding,
            payload=payload,
        )
    )


async def tombstone(
    product_id: ProductId, *, index: VectorIndex, clock: Clock, version: int
) -> None:
    """Помечает точку удалённой, сохраняя версию (§6.5)."""
    await index.set_payload(
        product_id,
        tombstone_fields(aggregate_version=version, deleted_at=clock.now()),
    )
