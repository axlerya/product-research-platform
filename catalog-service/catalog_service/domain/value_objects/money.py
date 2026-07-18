"""Value object ``Money`` — деньги на ``Decimal`` (float запрещён)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from catalog_service.domain.exceptions import CurrencyMismatchError
from catalog_service.domain.value_objects.currency import Currency

_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    """Денежная сумма с валютой.

    Сумма квантуется до двух знаков (``ROUND_HALF_UP``). ``float`` запрещён
    на всех границах — используйте ``Decimal`` или строку.

    Attributes:
        amount: Сумма (``Decimal``, scale=2). Может быть отрицательной
            (например, прибыль при убыточной марже).
        currency: Валюта суммы.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError(
                "Money не принимает float — используйте Decimal или str"
            )
        quantized = Decimal(self.amount).quantize(_CENTS, ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    @classmethod
    def of(cls, amount: Decimal | str | int, currency: Currency) -> "Money":
        """Создаёт ``Money`` из ``Decimal``/``str``/``int`` (но не float).

        Args:
            amount: Сумма как ``Decimal``, строка или целое.
            currency: Валюта.

        Returns:
            Новый экземпляр ``Money`` с квантованной суммой.
        """
        return cls(amount=amount, currency=currency)

    @classmethod
    def zero(cls, currency: Currency) -> "Money":
        """Возвращает нулевую сумму в заданной валюте."""
        return cls(amount=Decimal("0"), currency=currency)

    def __add__(self, other: "Money") -> "Money":
        self._ensure_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._ensure_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _ensure_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                "Нельзя оперировать деньгами в разных валютах: "
                f"{self.currency.code} и {other.currency.code}"
            )
