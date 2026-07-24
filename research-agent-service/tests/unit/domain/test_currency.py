"""Тесты value object Currency."""

from dataclasses import FrozenInstanceError

import pytest

from research_agent_service.domain.exceptions import (
    DomainError,
    InvalidCurrency,
)
from research_agent_service.domain.value_objects.currency import Currency


def test_valid_code_is_accepted() -> None:
    """Трёхбуквенный код из заглавных латинских букв допустим."""
    assert Currency("RUB").code == "RUB"


@pytest.mark.parametrize("bad_code", ["rub", "RU", "RUBB", "R1B", "РУБ", ""])
def test_invalid_code_is_rejected(bad_code: str) -> None:
    """Некорректный код валюты недопустим."""
    with pytest.raises(InvalidCurrency):
        Currency(bad_code)


def test_invalid_currency_is_domain_error() -> None:
    """InvalidCurrency — доменное исключение."""
    assert issubclass(InvalidCurrency, DomainError)


def test_currency_is_frozen() -> None:
    """Currency неизменяема."""
    currency = Currency("RUB")

    with pytest.raises(FrozenInstanceError):
        currency.code = "USD"
