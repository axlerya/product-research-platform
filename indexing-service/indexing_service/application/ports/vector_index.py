"""Порт ``VectorIndex`` — абстракция векторного хранилища (Qdrant)."""

from collections.abc import AsyncIterator, Mapping
from typing import Protocol

from indexing_service.application.dto.point import PointRecord, WatermarkEntry
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.watermark import IndexingWatermark


class VectorIndex(Protocol):
    """Запись/чтение поисковых точек с водяным знаком версии."""

    async def get_watermark(
        self, product_id: ProductId
    ) -> IndexingWatermark | None:
        """Возвращает водяной знак точки или ``None``, если точки нет."""
        ...

    def scroll_watermarks(self) -> AsyncIterator[WatermarkEntry]:
        """Итерирует водяные знаки всех точек (для reconcile-скана)."""
        ...

    async def upsert_document(self, point: PointRecord) -> None:
        """Пишет полную точку (векторы + payload) — created/repair."""
        ...

    async def update_vectors(
        self, product_id: ProductId, embedding: Embedding
    ) -> None:
        """Заменяет только векторы точки (ре-эмбеддинг), payload не трогает."""
        ...

    async def set_payload(
        self, product_id: ProductId, fields: Mapping[str, object]
    ) -> None:
        """Мержит поля payload; векторы не трогаются (§6.3)."""
        ...
