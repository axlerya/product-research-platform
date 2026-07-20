"""Порт ``EmbeddingResultSink`` — запись точек чанков (async-путь, §9.4).

Отдельный от ``VectorIndex`` (product-keyed) порт под chunked-модель: ключ —
``point_id``. Guard по ``content_version`` живёт в адаптере (не перезаписываем
свежую версию более старым результатом).
"""

from typing import Protocol

from indexing_service.application.dto.chunk_write import ChunkWrite


class EmbeddingResultSink(Protocol):
    """Пишет векторы+payload одной точки чанка (merge, guard по версии)."""

    async def apply_chunk(self, write: ChunkWrite) -> bool:
        """Пишет точку чанка.

        Returns:
            ``True``, если запись применена; ``False``, если пропущена как
            устаревшая (в Qdrant уже более свежая ``content_version``).
        """
        ...
