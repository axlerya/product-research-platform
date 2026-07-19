"""Value object ``DenseVector`` — плотный эмбеддинг (BGE-M3 dense)."""

import math
from dataclasses import dataclass

from indexing_service.domain.exceptions import InvalidVectorError


@dataclass(frozen=True, slots=True)
class DenseVector:
    """Плотный вектор из конечных чисел.

    Значения приводятся к ``float`` и замораживаются в кортеж. Соответствие
    размерности модели проверяется в ``Embedding``.

    Attributes:
        values: Компоненты вектора (кортеж ``float``).
    """

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        coerced = tuple(float(x) for x in self.values)
        if not coerced:
            raise InvalidVectorError("Плотный вектор не может быть пустым")
        if any(not math.isfinite(x) for x in coerced):
            raise InvalidVectorError(
                "Плотный вектор содержит бесконечность или NaN"
            )
        object.__setattr__(self, "values", coerced)

    @property
    def dimension(self) -> int:
        """Размерность вектора."""
        return len(self.values)
