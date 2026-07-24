"""Тесты value object Money (деньги на Decimal, float запрещён)."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.money import Money

_RUB = Currency("RUB")


def test_of_parses_string_amount() -> None:
    """Money.of парсит строковую сумму в Decimal."""
    money = Money.of("129.99", _RUB)

    assert money.amount == Decimal("129.99")
    assert money.currency == _RUB


def test_of_parses_int_and_quantizes_to_two_places() -> None:
    """Целое квантуется до двух знаков."""
    assert Money.of(100, _RUB).amount == Decimal("100.00")


def test_amount_is_rounded_half_up() -> None:
    """Сумма квантуется до сотых по правилу ROUND_HALF_UP."""
    assert Money(Decimal("1.005"), _RUB).amount == Decimal("1.01")


def test_negative_amount_is_allowed() -> None:
    """Отрицательная сумма допустима (например, убыточная прибыль)."""
    assert Money.of("-5.00", _RUB).amount == Decimal("-5.00")


def test_float_amount_is_rejected() -> None:
    """float запрещён на границе — только Decimal/str/int."""
    with pytest.raises(TypeError):
        Money(1.0, _RUB)
    with pytest.raises(TypeError):
        Money.of(1.0, _RUB)  # type: ignore[arg-type]


def test_money_equality_by_value() -> None:
    """Money равны по значению суммы и валюты."""
    assert Money.of("1.00", _RUB) == Money.of("1.00", _RUB)


def test_money_is_frozen() -> None:
    """Money неизменяемо."""
    money = Money.of("1.00", _RUB)

    with pytest.raises(FrozenInstanceError):
        money.amount = Decimal("2.00")
