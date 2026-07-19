"""Value object ``Pricing`` и детерминированный расчёт маржи.

Формула маржи дублирует ``catalog-service`` намеренно (payload считаем у
себя, без обратного вызова). Паритет закреплён контрактным тестом (§11.4).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from indexing_service.domain.exceptions import (
    CurrencyMismatchError,
    NegativeCostError,
    NegativePriceError,
)
from indexing_service.domain.value_objects.margin import Margin
from indexing_service.domain.value_objects.money import Money

_PERCENT_SCALE = Decimal("0.01")
_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class Pricing:
    """Цена и себестоимость товара (в одной валюте).

    Отрицательная маржа допускается (``cost`` может быть больше ``price``),
    но и цена, и себестоимость должны быть неотрицательными.

    Attributes:
        price: Текущая цена.
        cost: Себестоимость.
    """

    price: Money
    cost: Money

    def __post_init__(self) -> None:
        if self.price.amount < 0:
            raise NegativePriceError(
                f"Цена не может быть отрицательной: {self.price.amount}"
            )
        if self.cost.amount < 0:
            raise NegativeCostError(
                f"Себестоимость не может быть отрицательной: {self.cost.amount}"
            )
        if self.price.currency != self.cost.currency:
            raise CurrencyMismatchError(
                "Цена и себестоимость должны быть в одной валюте"
            )

    def calculate_margin(self) -> Margin:
        """Считает маржу по формуле ``(price - cost) / price * 100``.

        Returns:
            ``Margin`` с абсолютной прибылью и процентом. Процент равен
            ``None``, если цена равна нулю (маржа не определена).
        """
        profit = self.price - self.cost
        if self.price.amount == 0:
            return Margin(profit=profit, percent=None)
        percent = (
            (self.price.amount - self.cost.amount)
            / self.price.amount
            * _HUNDRED
        ).quantize(_PERCENT_SCALE, ROUND_HALF_UP)
        return Margin(profit=profit, percent=percent)
