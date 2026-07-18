"""Value object ``Margin`` — результат расчёта маржинальности."""

from dataclasses import dataclass
from decimal import Decimal

from catalog_service.domain.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class Margin:
    """Маржа товара.

    Attributes:
        profit: Абсолютная прибыль (цена минус себестоимость).
        percent: Процент маржи; ``None``, если цена равна нулю (маржа не
            определена).
    """

    profit: Money
    percent: Decimal | None
