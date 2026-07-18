"""Тесты сборки конверта события в ``OutboxMessage``."""

from uuid import UUID

import pytest

from catalog_service.application.event_mapping import (
    _build_data,
    build_outbox_message,
)
from catalog_service.domain.events import (
    ProductCommercialDataChanged,
    ProductContentChanged,
    ProductCreated,
    ProductDeleted,
)
from tests.support.factories import FIXED_NOW, make_product


def test_created_envelope_full_snapshot():
    product = make_product(sku="PROD-001")
    event = ProductCreated(product_id=product.id, occurred_at=FIXED_NOW)
    msg = build_outbox_message(event, product, message_id=UUID(int=7))

    assert msg.event_type == "catalog.product.created"
    assert msg.event_version == 1  # колонка = MAJOR
    assert msg.aggregate_version == product.version

    payload = msg.payload
    assert payload["event_version"] == "1.0"  # провод = semver-строка
    assert payload["producer"] == "catalog-service"
    assert payload["sku"] == "PROD-001"
    assert payload["event_id"] == str(UUID(int=7))
    assert payload["data"]["price"] == {
        "amount": "129.99",
        "currency": "RUB",
    }
    assert payload["data"]["metrics"]["avg_rating"] == "4.50"


def test_content_changed_carries_full_group():
    product = make_product()
    event = ProductContentChanged(
        product_id=product.id,
        changed_fields=("name",),
        occurred_at=FIXED_NOW,
    )
    data = build_outbox_message(event, product, message_id=UUID(int=1)).payload[
        "data"
    ]
    assert data["changed_fields"] == ["name"]
    assert set(data) >= {"name", "description", "category", "brand"}


def test_commercial_changed_carries_group():
    product = make_product()
    event = ProductCommercialDataChanged(
        product_id=product.id,
        changed_fields=("price", "stock"),
        occurred_at=FIXED_NOW,
    )
    data = build_outbox_message(event, product, message_id=UUID(int=1)).payload[
        "data"
    ]
    assert data["changed_fields"] == ["price", "stock"]
    assert set(data) >= {"price", "cost", "stock", "supplier"}


def test_deleted_envelope_is_identity_only():
    product = make_product(sku="PROD-001")
    event = ProductDeleted(product_id=product.id, occurred_at=FIXED_NOW)
    data = build_outbox_message(event, product, message_id=UUID(int=1)).payload[
        "data"
    ]
    assert data == {"product_id": str(product.id.value), "sku": "PROD-001"}


def test_unknown_event_raises():
    with pytest.raises(ValueError, match="Неизвестное событие"):
        _build_data(object(), make_product())
