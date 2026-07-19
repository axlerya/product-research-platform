"""Тесты сборки payload точки Qdrant (§4.4)."""

from datetime import UTC, datetime
from uuid import UUID

from indexing_service.application.payload import (
    commercial_payload,
    content_payload,
    full_payload,
    tombstone_fields,
)
from indexing_service.domain.entities.product_document import ProductDocument
from indexing_service.domain.value_objects.currency import Currency
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.money import Money
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.domain.value_objects.stock import StockLevel

_NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
RUB = Currency("RUB")


def _doc(**over) -> ProductDocument:
    fields = dict(
        product_id=ProductId(UUID(int=1)),
        sku=Sku("PROD-001"),
        name="X",
        description="Y",
        category="C",
        brand="B",
        supplier="S",
        pricing=Pricing(Money.of("129.99", RUB), Money.of("65.00", RUB)),
        stock=StockLevel(245),
        metrics=None,
        source_updated_at=None,
        aggregate_version=3,
    )
    fields.update(over)
    return ProductDocument(**fields)


def test_full_payload_shape_and_types():
    payload = full_payload(_doc(), model_version="m@v", indexed_at=_NOW)
    assert payload["price"] == 129.99
    assert isinstance(payload["price"], float)
    assert payload["in_stock"] is True
    assert payload["margin_percent"] == 50.0
    assert payload["currency"] == "RUB"
    assert payload["aggregate_version"] == 3
    assert payload["model_version"] == "m@v"
    assert payload["is_deleted"] is False
    assert len(payload["content_hash"]) == 64
    assert payload["indexed_at"] == "2026-07-19T10:15:30+00:00"


def test_full_payload_without_metrics_and_zero_price():
    payload = full_payload(
        _doc(
            pricing=Pricing(Money.zero(RUB), Money.of("4.00", RUB)),
            stock=StockLevel(0),
        ),
        model_version="m",
        indexed_at=_NOW,
    )
    assert payload["sales_per_month"] is None
    assert payload["rating"] is None
    assert payload["review_count"] is None
    assert payload["in_stock"] is False
    assert payload["source_updated_at"] is None
    assert payload["margin_percent"] is None


def test_commercial_payload_has_only_commercial_fields():
    payload = commercial_payload(
        pricing=Pricing(Money.of("99.99", RUB), Money.of("65.00", RUB)),
        stock=StockLevel(0),
        supplier="NewSup",
        aggregate_version=6,
        indexed_at=_NOW,
    )
    assert payload["price"] == 99.99
    assert payload["in_stock"] is False
    assert payload["supplier"] == "NewSup"
    assert payload["aggregate_version"] == 6
    assert "name" not in payload


def test_content_payload_has_only_content_fields():
    payload = content_payload(
        name="N",
        description="D",
        category="C",
        brand="B",
        content_hash="h",
        model_version="m",
        aggregate_version=6,
        indexed_at=_NOW,
    )
    assert payload["name"] == "N"
    assert payload["content_hash"] == "h"
    assert "price" not in payload


def test_tombstone_fields():
    payload = tombstone_fields(aggregate_version=8, deleted_at=_NOW)
    assert payload["is_deleted"] is True
    assert payload["aggregate_version"] == 8
    assert payload["deleted_at"] == "2026-07-19T10:15:30+00:00"
