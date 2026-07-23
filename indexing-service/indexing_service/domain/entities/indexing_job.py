"""Сущность ``IndexingJob`` — задание на индексацию товара (§8).

Иммутабельный снимок состояния задания: какие чанки товара на данной
``content_version`` должны быть проиндексированы и в каком они статусе.
Богатые переходы (пометка чанков, пересчёт статуса) добавляются в шаге,
который их использует (`ApplyEmbeddingResult`).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
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

    def mark_ok(self) -> "Chunk":
        """Успешный эмбеддинг: чанк записан в Qdrant."""
        return replace(self, status=ChunkStatus.OK)

    def mark_retrying(self) -> "Chunk":
        """Транзиентный сбой: ставим на повтор (счётчик попыток +1)."""
        return replace(
            self, status=ChunkStatus.RETRYING, attempts=self.attempts + 1
        )

    def mark_failed(self) -> "Chunk":
        """Перманентный отказ: чанк не будет проиндексирован."""
        return replace(self, status=ChunkStatus.FAILED)


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

    @property
    def is_terminal(self) -> bool:
        """Достигла ли job финального состояния (``DONE``/``FAILED``)."""
        return self.status in (JobStatus.DONE, JobStatus.FAILED)

    def chunk_by_text_id(self, text_id: str) -> Chunk:
        """Возвращает чанк по ``text_id``.

        Raises:
            InvalidJobError: Если чанк с таким ``text_id`` не найден.
        """
        for chunk in self.chunks:
            if chunk.text_id == text_id:
                return chunk
        raise InvalidJobError(f"чанк не найден: text_id={text_id!r}")

    def mark_chunk_ok(self, text_id: str) -> "IndexingJob":
        """Помечает чанк успешным (записан в Qdrant)."""
        return self._map_chunk(text_id, Chunk.mark_ok)

    def mark_chunk_retrying(self, text_id: str) -> "IndexingJob":
        """Ставит чанк на повтор (транзиентный сбой)."""
        return self._map_chunk(text_id, Chunk.mark_retrying)

    def mark_chunk_failed(self, text_id: str) -> "IndexingJob":
        """Помечает чанк перманентно упавшим."""
        return self._map_chunk(text_id, Chunk.mark_failed)

    def rechunk(
        self, text_id: str, replacements: Sequence[Chunk]
    ) -> "IndexingJob":
        """Заменяет чанк под-чанками после дробления текста (Q2 §8).

        Под-чанки встают на место исходного, порядок остальных сохраняется.

        Raises:
            InvalidJobError: Если чанк не найден или замена пуста.
        """
        if not replacements:
            raise InvalidJobError("замена чанка требует хотя бы под-чанк")
        self.chunk_by_text_id(text_id)  # проверка наличия
        chunks: list[Chunk] = []
        for chunk in self.chunks:
            if chunk.text_id == text_id:
                chunks.extend(replacements)
            else:
                chunks.append(chunk)
        return replace(self, chunks=tuple(chunks))

    def recompute_status(self) -> "IndexingJob":
        """Пересчитывает статус job из статусов чанков (§8)."""
        return replace(self, status=self._derive_status())

    def _map_chunk(self, text_id: str, transition) -> "IndexingJob":
        self.chunk_by_text_id(text_id)  # проверка наличия
        chunks = tuple(
            transition(chunk) if chunk.text_id == text_id else chunk
            for chunk in self.chunks
        )
        return replace(self, chunks=chunks)

    def _derive_status(self) -> JobStatus:
        statuses = {chunk.status for chunk in self.chunks}
        in_flight = statuses & {ChunkStatus.PENDING, ChunkStatus.RETRYING}
        if not in_flight:
            # Терминал: остались только ok/failed.
            return (
                JobStatus.DONE
                if ChunkStatus.FAILED not in statuses
                else JobStatus.FAILED
            )
        # Ещё в процессе: ждём результаты по части чанков.
        if ChunkStatus.FAILED in statuses or ChunkStatus.RETRYING in statuses:
            return JobStatus.PARTIALLY_FAILED
        return JobStatus.AWAITING
