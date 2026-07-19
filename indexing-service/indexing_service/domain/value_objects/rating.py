"""Value object ``Rating`` — средний рейтинг 0..5, scale=2."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from indexing_service.domain.exceptions import InvalidRatingError

_SCALE = Decimal("0.01")
_MIN = Decimal("0")
_MAX = Decimal("5")


@dataclass(frozen=True, slots=True)
class Rating:
    """Средний рейтинг товара в диапазоне [0..5].

    Attributes:
        value: Значение рейтинга (``Decimal``, scale=2).
    """

    value: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            raise TypeError(
                "Rating не принимает float — используйте Decimal или str"
            )
        quantized = Decimal(self.value).quantize(_SCALE, ROUND_HALF_UP)
        if not _MIN <= quantized <= _MAX:
            raise InvalidRatingError(
                f"Рейтинг должен быть в [0..5], получено: {quantized}"
            )
        object.__setattr__(self, "value", quantized)
