"""Value object ``BatchEmbeddingResult`` — упорядоченный результат батча."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)


@dataclass(frozen=True, slots=True)
class BatchEmbeddingResult:
    """Результат батча; порядок ``items`` строго равен порядку входа.

    Attributes:
        model_id: Идентификатор породившей модели.
        items: Пер-элементные результаты в порядке входа.
    """

    model_id: EmbeddingModelId
    items: tuple[EmbeddingItemResult, ...]

    @property
    def all_ok(self) -> bool:
        """Все ли элементы успешны."""
        return all(item.is_ok for item in self.items)

    @property
    def has_errors(self) -> bool:
        """Есть ли хотя бы один отказ."""
        return any(not item.is_ok for item in self.items)
