"""Тесты value object ``Currency`` (ISO-4217 alpha-3)."""

import pytest

from indexing_service.domain.exceptions import InvalidCurrencyError
from indexing_service.domain.value_objects.currency import Currency


def test_valid_code():
    assert Currency("RUB").code == "RUB"


def test_rejects_lowercase():
    with pytest.raises(InvalidCurrencyError):
        Currency("rub")


def test_rejects_wrong_length():
    with pytest.raises(InvalidCurrencyError):
        Currency("RU")


def test_equality_by_value():
    assert Currency("USD") == Currency("USD")
    assert Currency("USD") != Currency("RUB")
