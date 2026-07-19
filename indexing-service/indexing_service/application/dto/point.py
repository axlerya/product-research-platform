"""DTO точек Qdrant: полная точка для upsert и знак для reconcile."""

from dataclasses import dataclass

from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.watermark import IndexingWatermark


@dataclass(frozen=True, slots=True)
class PointRecord:
    """Полная точка для ``upsert`` (создание/repair).

    Attributes:
        product_id: Идентификатор товара (= id точки Qdrant).
        embedding: Dense + sparse векторы и модель.
        payload: Готовый payload (плоские типы для Qdrant).
    """

    product_id: ProductId
    embedding: Embedding
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class WatermarkEntry:
    """Водяной знак одной точки (для reconcile-скана).

    Attributes:
        product_id: Идентификатор товара.
        watermark: Текущий водяной знак точки.
        is_deleted: Помечена ли точка удалённой (tombstone).
    """

    product_id: ProductId
    watermark: IndexingWatermark
    is_deleted: bool
