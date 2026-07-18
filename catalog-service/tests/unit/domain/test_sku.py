"""Тесты value object ``Sku`` (нормализация и валидация)."""

import pytest

from catalog_service.domain.exceptions import InvalidSku
from catalog_service.domain.value_objects.sku import Sku


def test_normalizes_whitespace_and_case():
    assert Sku("  prod-001 ").value == "PROD-001"


def test_equality_ignores_original_case():
    assert Sku("prod-1") == Sku("PROD-1")
    assert hash(Sku("prod-1")) == hash(Sku("PROD-1"))


def test_non_prod_prefix_is_valid():
    assert Sku("ABC-9").value == "ABC-9"


@pytest.mark.parametrize("raw", ["", "A", "AB", "PR@D", "ABC-", "-ABC"])
def test_invalid_sku_raises(raw):
    with pytest.raises(InvalidSku):
        Sku(raw)
