"""Тесты value object ``ProductMetrics``."""

from decimal import Decimal

import pytest

from catalog_service.domain.exceptions import NegativeMetricError
from catalog_service.domain.value_objects.metrics import ProductMetrics
from catalog_service.domain.value_objects.rating import Rating


def _rating() -> Rating:
    return Rating(Decimal("4.50"))


def test_valid_metrics():
    metrics = ProductMetrics(87, _rating(), 1243)
    assert metrics.sales_per_month == 87
    assert metrics.review_count == 1243
    assert metrics.avg_rating.value == Decimal("4.50")


def test_zero_values_ok():
    metrics = ProductMetrics(0, _rating(), 0)
    assert metrics.sales_per_month == 0


def test_negative_sales_raises():
    with pytest.raises(NegativeMetricError):
        ProductMetrics(-1, _rating(), 0)


def test_negative_reviews_raises():
    with pytest.raises(NegativeMetricError):
        ProductMetrics(0, _rating(), -1)
