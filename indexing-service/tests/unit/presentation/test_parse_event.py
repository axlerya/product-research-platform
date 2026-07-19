"""Тесты разбора конверта события (§3.3)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from indexing_service.application.dto.events import (
    CommercialChangedEvent,
    ContentChangedEvent,
    ProductCreatedEvent,
    ProductDeletedEvent,
)
from indexing_service.application.exceptions import EventValidationError
from indexing_service.presentation.messaging.parsing import parse_event
from indexing_service.presentation.messaging.schemas import CatalogEnvelope

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
PID = UUID("0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a")

_CREATED_DATA = {
    "product_id": str(PID),
    "sku": "PROD-001",
    "name": "Наушники",
    "description": "Беспроводные",
    "category": "Электроника",
    "brand": "AudioMax",
    "supplier": "TechSupply",
    "price": {"amount": "129.99", "currency": "RUB"},
    "cost": {"amount": "65.00", "currency": "RUB"},
    "stock": 245,
    "metrics": {
        "sales_per_month": 87,
        "avg_rating": "4.50",
        "review_count": 1243,
    },
    "source_updated_at": "2024-03-15",
}


def _env(event_type: str, data: dict, version: int = 1) -> CatalogEnvelope:
    return CatalogEnvelope(
        event_id=UUID(int=1),
        event_type=event_type,
        aggregate_id=PID,
        sku="PROD-001",
        aggregate_version=version,
        occurred_at=NOW,
        data=data,
    )


def test_parse_created():
    event = parse_event(_env("catalog.product.created", _CREATED_DATA, 1))
    assert isinstance(event, ProductCreatedEvent)
    assert event.product.price == Decimal("129.99")
    assert event.product.avg_rating == Decimal("4.50")
    assert event.product.sales_per_month == 87
    assert event.aggregate_version == 1


def test_parse_content_changed():
    data = {
        "changed_fields": ["name"],
        "name": "Новое имя",
        "description": "D",
        "category": "C",
        "brand": "B",
    }
    event = parse_event(_env("catalog.product.content_changed", data, 6))
    assert isinstance(event, ContentChangedEvent)
    assert event.name == "Новое имя"
    assert event.changed_fields == ("name",)
    assert event.product_id == PID


def test_parse_commercial_changed():
    data = {
        "changed_fields": ["price", "stock"],
        "price": {"amount": "119.99", "currency": "RUB"},
        "cost": {"amount": "65.00", "currency": "RUB"},
        "stock": 230,
        "supplier": "TechSupply",
    }
    event = parse_event(
        _env("catalog.product.commercial_data_changed", data, 6)
    )
    assert isinstance(event, CommercialChangedEvent)
    assert event.price == Decimal("119.99")
    assert event.stock == 230


def test_parse_deleted():
    data = {"product_id": str(PID), "sku": "PROD-001"}
    event = parse_event(_env("catalog.product.deleted", data, 7))
    assert isinstance(event, ProductDeletedEvent)
    assert event.aggregate_version == 7


def test_unknown_type_raises():
    with pytest.raises(EventValidationError):
        parse_event(_env("catalog.product.frobnicated", {}, 1))


def test_malformed_data_raises():
    with pytest.raises(EventValidationError):
        parse_event(
            _env("catalog.product.commercial_data_changed", {"stock": 1}, 1)
        )
