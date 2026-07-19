"""Тесты value object ``Rating`` (0..5, scale=2, без float)."""

from decimal import Decimal

import pytest

from indexing_service.domain.exceptions import InvalidRatingError
from indexing_service.domain.value_objects.rating import Rating


def test_quantizes_two_places():
    assert Rating(Decimal("4.5")).value == Decimal("4.50")


def test_accepts_string():
    assert Rating("0").value == Decimal("0.00")


def test_rejects_float():
    with pytest.raises(TypeError):
        Rating(4.5)


def test_rejects_out_of_range_high():
    with pytest.raises(InvalidRatingError):
        Rating(Decimal("5.01"))


def test_rejects_negative():
    with pytest.raises(InvalidRatingError):
        Rating(Decimal("-0.01"))
