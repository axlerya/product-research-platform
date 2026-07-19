"""Тесты value object ``Sku`` (нормализация + regex)."""

import pytest

from indexing_service.domain.exceptions import InvalidSku
from indexing_service.domain.value_objects.sku import Sku


def test_normalizes_upper_and_strip():
    assert Sku("  prod-001 ").value == "PROD-001"


def test_rejects_too_short():
    with pytest.raises(InvalidSku):
        Sku("A")


def test_rejects_invalid_chars():
    with pytest.raises(InvalidSku):
        Sku("PROD_001")


def test_equality_by_value_after_normalization():
    assert Sku("prod-1a") == Sku("PROD-1A")
