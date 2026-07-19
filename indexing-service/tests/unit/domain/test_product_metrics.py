"""Тесты value object ``ProductMetrics``."""

from decimal import Decimal

import pytest

from indexing_service.domain.exceptions import NegativeMetricError
from indexing_service.domain.value_objects.metrics import ProductMetrics
from indexing_service.domain.value_objects.rating import Rating


def _metrics(sales: int = 10, rating: str = "4.50", reviews: int = 100):
    return ProductMetrics(
        sales_per_month=sales,
        avg_rating=Rating(Decimal(rating)),
        review_count=reviews,
    )


def test_valid():
    metrics = _metrics()
    assert metrics.sales_per_month == 10
    assert metrics.review_count == 100
    assert metrics.avg_rating.value == Decimal("4.50")


def test_rejects_negative_sales():
    with pytest.raises(NegativeMetricError):
        _metrics(sales=-1)


def test_rejects_negative_reviews():
    with pytest.raises(NegativeMetricError):
        _metrics(reviews=-1)
