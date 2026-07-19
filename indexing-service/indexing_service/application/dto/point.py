"""DTO ``PointRecord`` — точка Qdrant (векторы + payload) для upsert."""

from dataclasses import dataclass

from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.identifiers import ProductId


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
