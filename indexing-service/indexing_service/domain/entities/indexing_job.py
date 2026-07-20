"""Сущность ``IndexingJob`` — задание на индексацию товара (§8).

Иммутабельный снимок состояния задания: какие чанки товара на данной
``content_version`` должны быть проиндексированы и в каком они статусе.
Богатые переходы (пометка чанков, пересчёт статуса) добавляются в шаге,
который их использует (`ApplyEmbeddingResult`).
"""

from dataclasses import dataclass
from datetime import datetime

from indexing_service.domain.exceptions import InvalidJobError
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import JobId, ProductId
from indexing_service.domain.value_objects.job_status import (
    ChunkStatus,
    IndexAction,
    JobStatus,
)
from indexing_service.domain.value_objects.sku import Sku


@dataclass(frozen=True, slots=True)
class Chunk:
    """Чанк товара, соответствующий одной точке Qdrant.

    Attributes:
        chunk_ix: Порядковый индекс чанка.
        text_id: Идентификатор элемента в команде (== id точки Qdrant).
        point_id: Идентификатор точки Qdrant.
        status: Статус чанка.
        attempts: Число попыток эмбеддинга.
    """

    chunk_ix: int
    text_id: str
    point_id: str
    status: ChunkStatus
    attempts: int

    def __post_init__(self) -> None:
        if self.chunk_ix < 0:
            raise InvalidJobError(f"chunk_ix < 0: {self.chunk_ix}")
        if not self.text_id:
            raise InvalidJobError("text_id чанка не может быть пустым")
        if not self.point_id:
            raise InvalidJobError("point_id чанка не может быть пустым")
        if self.attempts < 0:
            raise InvalidJobError(f"attempts < 0: {self.attempts}")


@dataclass(frozen=True, slots=True)
class IndexingJob:
    """Задание на индексацию товара (агрегат).

    Attributes:
        job_id: Идентификатор задания.
        product_id: Идентификатор товара.
        sku: Артикул.
        aggregate_version: Версия агрегата товара (>= 1).
        content_version: Версия текста, на которой считаются векторы (>= 1).
        content_hash: Хэш проиндексированного текста.
        action: Тип индексации.
        target_collection: Целевая коллекция (для reindex; иначе alias).
        expected_model: Ожидаемый ключ модели (или ``None``).
        status: Статус задания.
        chunks: Чанки товара (>= 1, уникальные ``text_id``).
        created_at/updated_at: Времена жизни.
        applied_at: Момент финального применения (или ``None``).
    """

    job_id: JobId
    product_id: ProductId
    sku: Sku
    aggregate_version: int
    content_version: int
    content_hash: ContentHash
    action: IndexAction
    target_collection: str | None
    expected_model: str | None
    status: JobStatus
    chunks: tuple[Chunk, ...]
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None

    def __post_init__(self) -> None:
        if self.aggregate_version < 1:
            raise InvalidJobError(
                f"aggregate_version < 1: {self.aggregate_version}"
            )
        if self.content_version < 1:
            raise InvalidJobError(
                f"content_version < 1: {self.content_version}"
            )
        if not self.chunks:
            raise InvalidJobError("у job должен быть хотя бы один чанк")
        text_ids = [chunk.text_id for chunk in self.chunks]
        if len(set(text_ids)) != len(text_ids):
            raise InvalidJobError("text_id чанков должны быть уникальны")
