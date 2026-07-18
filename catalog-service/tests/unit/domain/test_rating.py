"""Тесты value object ``Rating`` (0..5, scale=2)."""

from decimal import Decimal

import pytest

from catalog_service.domain.exceptions import InvalidRatingError
from catalog_service.domain.value_objects.rating import Rating


def test_boundaries_ok():
    assert Rating(Decimal("0")).value == Decimal("0.00")
    assert Rating(Decimal("5")).value == Decimal("5.00")
    assert Rating(Decimal("4.5")).value == Decimal("4.50")


def test_quantizes_half_up():
    assert Rating(Decimal("4.505")).value == Decimal("4.51")


@pytest.mark.parametrize("value", ["-0.1", "5.01", "6"])
def test_out_of_range_raises(value):
    with pytest.raises(InvalidRatingError):
        Rating(Decimal(value))


def test_rejects_float():
    with pytest.raises(TypeError):
        Rating(4.5)
