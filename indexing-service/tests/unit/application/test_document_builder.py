"""Тесты ``to_product_document`` (снимок catalog → доменная сущность)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from indexing_service.application.document_builder import to_product_document
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.domain.exceptions import NegativeStockError

_PID = UUID("0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a")


def _snapshot(**over) -> ProductSnapshot:
    fields = dict(
        product_id=_PID,
        sku="PROD-001",
        name="Наушники",
        description="Беспроводные",
        category="Электроника",
        brand="AudioMax",
        supplier="TechSupply",
        price=Decimal("129.99"),
        cost=Decimal("65.00"),
        currency="RUB",
        stock=245,
        sales_per_month=87,
        avg_rating=Decimal("4.5"),
        review_count=1243,
        source_updated_at=date(2024, 3, 15),
        aggregate_version=1,
    )
    fields.update(over)
    return ProductSnapshot(**fields)


def test_builds_document_with_vos():
    doc = to_product_document(_snapshot())
    assert doc.sku.value == "PROD-001"
    assert doc.pricing.price.amount == Decimal("129.99")
    assert doc.margin().percent == Decimal("50.00")
    assert doc.metrics.review_count == 1243
    assert "Товар: Наушники" in doc.search_text().value


def test_invalid_snapshot_raises_domain_error():
    with pytest.raises(NegativeStockError):
        to_product_document(_snapshot(stock=-1))
