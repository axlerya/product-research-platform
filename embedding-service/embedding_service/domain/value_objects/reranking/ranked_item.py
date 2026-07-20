"""Value object ``RankedItem`` — один документ с его скором и позицией."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.reranking.exceptions import (
    InvalidRankedItemError,
)
from embedding_service.domain.value_objects.reranking.relevance_score import (
    RelevanceScore,
)
from embedding_service.domain.value_objects.text_id import TextId


@dataclass(frozen=True, slots=True)
class RankedItem:
    """Оценённый документ: id, исходная позиция и скор релевантности.

    ``index`` — позиция документа во входном запросе (0-based); сохраняется,
    чтобы клиент сопоставил результат со своим входом после переупорядочивания
    и отсечения top_n.

    Attributes:
        text_id: Идентификатор документа (корреляция).
        index: Исходная позиция во входе, >= 0.
        score: Скор релевантности запросу.
    """

    text_id: TextId
    index: int
    score: RelevanceScore

    def __post_init__(self) -> None:
        if self.index < 0:
            raise InvalidRankedItemError(
                f"Индекс должен быть >= 0: {self.index}"
            )
