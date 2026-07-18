"""Тесты value object ``Currency``."""

import pytest

from catalog_service.domain.exceptions import InvalidCurrencyError
from catalog_service.domain.value_objects.currency import Currency


def test_valid_iso_code():
    assert Currency("RUB").code == "RUB"


@pytest.mark.parametrize("code", ["rub", "RU", "RUBB", "12X", "", "R U"])
def test_invalid_code_raises(code):
    with pytest.raises(InvalidCurrencyError):
        Currency(code)


def test_equality_by_value():
    assert Currency("USD") == Currency("USD")
    assert Currency("USD") != Currency("RUB")
