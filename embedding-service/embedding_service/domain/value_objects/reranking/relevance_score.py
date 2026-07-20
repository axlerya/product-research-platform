"""Value object ``RelevanceScore`` — скор релевантности пары (query, doc)."""

import math
from dataclasses import dataclass

from embedding_service.domain.value_objects.reranking.exceptions import (
    InvalidScoreError,
)


@dataclass(frozen=True, slots=True)
class RelevanceScore:
    """Скор релевантности одного документа запросу.

    Допускается любое конечное значение: ненормированный скор — логит (может
    быть отрицательным), нормированный — вероятность в ``[0, 1]``.

    Attributes:
        value: Конечное вещественное значение скора.
    """

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise InvalidScoreError(
                f"Скор должен быть конечным числом: {self.value}"
            )
