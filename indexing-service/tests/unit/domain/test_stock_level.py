"""Тесты value object ``StockLevel`` (>= 0, is_in_stock)."""

import pytest

from indexing_service.domain.exceptions import NegativeStockError
from indexing_service.domain.value_objects.stock import StockLevel


def test_in_stock_true_when_positive():
    assert StockLevel(5).is_in_stock is True


def test_in_stock_false_when_zero():
    assert StockLevel(0).is_in_stock is False


def test_rejects_negative():
    with pytest.raises(NegativeStockError):
        StockLevel(-1)
