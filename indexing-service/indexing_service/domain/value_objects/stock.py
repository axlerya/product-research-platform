"""Value object ``StockLevel`` — остаток на складе (>= 0)."""

from dataclasses import dataclass

from indexing_service.domain.exceptions import NegativeStockError


@dataclass(frozen=True, slots=True)
class StockLevel:
    """Неотрицательный остаток товара на складе.

    Attributes:
        quantity: Количество единиц на складе.
    """

    quantity: int

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise NegativeStockError(
                f"Остаток не может быть отрицательным: {self.quantity}"
            )

    @property
    def is_in_stock(self) -> bool:
        """Возвращает ``True``, если товар в наличии (остаток > 0)."""
        return self.quantity > 0
