"""Value object ``SparseVector`` — разрежённый эмбеддинг (BGE-M3 lexical)."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from indexing_service.domain.exceptions import InvalidVectorError


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Разрежённый вектор в канонической форме.

    Индексы отсортированы по возрастанию, уникальны и неотрицательны;
    значения конечны и ненулевы. Пустой вектор допускается.

    Attributes:
        indices: Индексы ненулевых компонент (токен-id BGE-M3).
        values: Веса соответствующих компонент.
    """

    indices: tuple[int, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        indices = tuple(self.indices)
        values = tuple(float(v) for v in self.values)
        if len(indices) != len(values):
            raise InvalidVectorError(
                "Длины indices и values не совпадают"
            )
        if any(i < 0 for i in indices):
            raise InvalidVectorError("Индекс не может быть отрицательным")
        if len(set(indices)) != len(indices):
            raise InvalidVectorError("Индексы должны быть уникальны")
        if list(indices) != sorted(indices):
            raise InvalidVectorError("Индексы должны быть отсортированы")
        if any(not math.isfinite(v) or v == 0.0 for v in values):
            raise InvalidVectorError("Значение нулевое или не конечно")
        object.__setattr__(self, "indices", indices)
        object.__setattr__(self, "values", values)

    @classmethod
    def from_mapping(cls, weights: Mapping[int, float]) -> Self:
        """Строит канонический вектор из отображения ``index -> weight``.

        Нулевые веса отбрасываются; индексы сортируются по возрастанию.

        Args:
            weights: Отображение токен-id в вес.

        Returns:
            Канонический ``SparseVector``.
        """
        nonzero = [
            (i, float(w)) for i, w in weights.items() if float(w) != 0.0
        ]
        nonzero.sort(key=lambda pair: pair[0])
        indices = tuple(i for i, _ in nonzero)
        values = tuple(w for _, w in nonzero)
        return cls(indices=indices, values=values)

    def to_mapping(self) -> dict[int, float]:
        """Возвращает представление ``index -> weight``."""
        return dict(zip(self.indices, self.values, strict=True))
