"""Value object ``RerankResult`` — упорядоченный результат ранжирования."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.reranking.ranked_item import (
    RankedItem,
)
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)


@dataclass(frozen=True, slots=True)
class RerankResult:
    """Итог ранжирования: модель + элементы по убыванию скора (с учётом top_n).

    Attributes:
        model_id: Идентификатор породившей reranker-модели.
        items: Ранжированные элементы (уже отсортированы и усечены до top_n).
    """

    model_id: RerankerModelId
    items: tuple[RankedItem, ...]

    @property
    def size(self) -> int:
        """Число элементов в результате."""
        return len(self.items)
