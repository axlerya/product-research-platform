"""Value object ``TopN`` — сколько верхних результатов вернуть."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.reranking.exceptions import (
    InvalidTopNError,
)


@dataclass(frozen=True, slots=True)
class TopN:
    """Ограничение выдачи верхними ``value`` результатами (по убыванию скора).

    Отсутствие ограничения (вернуть все) моделируется как ``None`` на границе
    use case, а не отдельным значением здесь.

    Attributes:
        value: Число верхних результатов, строго положительное.
    """

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise InvalidTopNError(f"top_n должно быть > 0: {self.value}")
