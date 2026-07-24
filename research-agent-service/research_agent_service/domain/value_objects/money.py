"""Value object Money — деньги на Decimal (float запрещён).

Агент деньги не вычисляет (маржу и статистики считает catalog): Money —
read-only носитель суммы, разобранной из строки на границе адаптера.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from research_agent_service.domain.value_objects.currency import Currency

_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    """Денежная сумма с валютой.

    Сумма квантуется до двух знаков (``ROUND_HALF_UP``). ``float`` запрещён
    на всех границах — используйте ``Decimal``, ``str`` или ``int``.

    Attributes:
        amount: Сумма (``Decimal``, scale=2). Может быть отрицательной.
        currency: Валюта суммы.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError(
                "Money не принимает float — используйте Decimal, str или int"
            )
        quantized = Decimal(self.amount).quantize(_CENTS, ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    @classmethod
    def of(cls, amount: Decimal | str | int, currency: Currency) -> "Money":
        """Создаёт ``Money`` из ``Decimal``/``str``/``int`` (но не float)."""
        return cls(amount=amount, currency=currency)
