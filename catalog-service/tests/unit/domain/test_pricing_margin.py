"""Тесты ``Pricing`` и детерминированного расчёта маржи."""

from decimal import Decimal

import pytest

from catalog_service.domain.exceptions import (
    CurrencyMismatchError,
    NegativeCostError,
    NegativePriceError,
)
from catalog_service.domain.value_objects.currency import Currency
from catalog_service.domain.value_objects.money import Money
from catalog_service.domain.value_objects.pricing import Pricing

RUB = Currency("RUB")
USD = Currency("USD")


def _pricing(price: str, cost: str, currency: Currency = RUB) -> Pricing:
    return Pricing(
        price=Money.of(price, currency),
        cost=Money.of(cost, currency),
    )


def test_regular_margin():
    margin = _pricing("129.99", "65.00").calculate_margin()
    assert margin.percent == Decimal("50.00")
    assert margin.profit.amount == Decimal("64.99")


def test_zero_price_margin_is_none():
    margin = _pricing("0", "65.00").calculate_margin()
    assert margin.percent is None
    assert margin.profit.amount == Decimal("-65.00")


def test_negative_margin_allowed():
    margin = _pricing("80.00", "100.00").calculate_margin()
    assert margin.percent == Decimal("-25.00")
    assert margin.profit.amount == Decimal("-20.00")


def test_negative_price_raises():
    with pytest.raises(NegativePriceError):
        _pricing("-1.00", "0.00")


def test_negative_cost_raises():
    with pytest.raises(NegativeCostError):
        _pricing("10.00", "-1.00")


def test_currency_mismatch_raises():
    with pytest.raises(CurrencyMismatchError):
        Pricing(Money.of("10.00", RUB), Money.of("5.00", USD))
