"""Тесты value object ``StockLevel``."""

import pytest

from catalog_service.domain.exceptions import NegativeStockError
from catalog_service.domain.value_objects.stock import StockLevel


def test_zero_is_out_of_stock():
    level = StockLevel(0)
    assert level.quantity == 0
    assert level.is_in_stock is False


def test_positive_is_in_stock():
    assert StockLevel(5).is_in_stock is True


def test_negative_raises():
    with pytest.raises(NegativeStockError):
        StockLevel(-1)
