"""Тесты value object ``Money`` (Decimal-деньги, без float)."""

from decimal import Decimal

import pytest

from catalog_service.domain.exceptions import CurrencyMismatchError
from catalog_service.domain.value_objects.currency import Currency
from catalog_service.domain.value_objects.money import Money

RUB = Currency("RUB")
USD = Currency("USD")


def test_quantizes_two_places_half_up():
    assert Money.of("1.005", RUB).amount == Decimal("1.01")


def test_of_accepts_decimal():
    assert Money.of(Decimal("129.99"), RUB).amount == Decimal("129.99")


def test_of_rejects_float():
    with pytest.raises(TypeError):
        Money.of(1.005, RUB)


def test_zero():
    assert Money.zero(RUB).amount == Decimal("0.00")


def test_add_same_currency():
    total = Money.of("10.00", RUB) + Money.of("5.50", RUB)
    assert total.amount == Decimal("15.50")


def test_add_different_currency_raises():
    with pytest.raises(CurrencyMismatchError):
        _ = Money.of("10.00", RUB) + Money.of("5.00", USD)


def test_sub_different_currency_raises():
    with pytest.raises(CurrencyMismatchError):
        _ = Money.of("10.00", RUB) - Money.of("5.00", USD)


def test_sub_negative_result_allowed():
    diff = Money.of("5.00", RUB) - Money.of("8.00", RUB)
    assert diff.amount == Decimal("-3.00")


def test_equality_by_value_and_currency():
    assert Money.of("10.00", RUB) == Money.of("10.00", RUB)
    assert Money.of("10.00", RUB) != Money.of("10.00", USD)
