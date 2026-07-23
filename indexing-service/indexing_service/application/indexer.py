"""Разделяемые операции индексации (consumer + batch use cases).

``index_snapshot`` («снимок → эмбеддинг → upsert») удалён вместе с переходом
на async-эмбеддинг: последние его вызывающие — reindex и reconcile —
переведены на job-модель. Осталось то, что embedding-service не касается.
"""

from indexing_service.application.payload import tombstone_fields
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.domain.value_objects.identifiers import ProductId


async def tombstone(
    product_id: ProductId, *, index: VectorIndex, clock: Clock, version: int
) -> None:
    """Помечает точку удалённой, сохраняя версию (§6.5)."""
    await index.set_payload(
        product_id,
        tombstone_fields(aggregate_version=version, deleted_at=clock.now()),
    )
