"""Value object ``IndexingWatermark`` — водяной знак индексации точки."""

from dataclasses import dataclass
from datetime import datetime

from indexing_service.domain.exceptions import InvalidWatermarkError
from indexing_service.domain.value_objects.content_hash import ContentHash


@dataclass(frozen=True, slots=True)
class IndexingWatermark:
    """Отметка «что уже применено» на точку Qdrant.

    Читается из payload и используется доменной классификацией для строгого
    guard'а по версии (см. ``ChangeClassifier``).

    Attributes:
        aggregate_version: Версия агрегата товара (>= 1).
        model_version: Ключ модели, которой построены векторы.
        content_hash: Хэш проиндексированного текста (или ``None``).
        indexed_at: Момент последней записи.
    """

    aggregate_version: int
    model_version: str
    content_hash: ContentHash | None
    indexed_at: datetime

    def __post_init__(self) -> None:
        if self.aggregate_version < 1:
            raise InvalidWatermarkError(
                f"Версия агрегата должна быть >= 1: {self.aggregate_version}"
            )
