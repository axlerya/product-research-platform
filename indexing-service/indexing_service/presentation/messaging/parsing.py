"""Разбор конверта → application-DTO ``CatalogEvent`` (§3.3).

Деньги/рейтинг на проводе — строкой → ``Decimal``. Метрики в событии
``created`` вложены в ``data.metrics`` (в отличие от REST, где top-level).
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from indexing_service.application.dto.events import (
    CatalogEvent,
    CommercialChangedEvent,
    ContentChangedEvent,
    ProductCreatedEvent,
    ProductDeletedEvent,
)
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.exceptions import EventValidationError
from indexing_service.presentation.messaging.schemas import CatalogEnvelope

_CREATED = "catalog.product.created"
_CONTENT = "catalog.product.content_changed"
_COMMERCIAL = "catalog.product.commercial_data_changed"
_DELETED = "catalog.product.deleted"

_PARSE_ERRORS = (KeyError, TypeError, ValueError, InvalidOperation)


def parse_event(envelope: CatalogEnvelope) -> CatalogEvent:
    """Маппит конверт в типизированное событие.

    Raises:
        EventValidationError: Неизвестный тип или неразбираемый ``data``
            (poison → DLQ).
    """
    try:
        return _parse(envelope)
    except _PARSE_ERRORS as exc:
        raise EventValidationError(
            f"не удалось разобрать {envelope.event_type}: {exc}"
        ) from exc


def _parse(envelope: CatalogEnvelope) -> CatalogEvent:
    data = envelope.data
    version = envelope.aggregate_version
    if envelope.event_type == _CREATED:
        return ProductCreatedEvent(
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
            product=_snapshot(data, version),
        )
    if envelope.event_type == _CONTENT:
        return ContentChangedEvent(
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
            product_id=envelope.aggregate_id,
            sku=envelope.sku,
            aggregate_version=version,
            changed_fields=tuple(data.get("changed_fields", ())),
            name=data["name"],
            description=data["description"],
            category=data["category"],
            brand=data["brand"],
        )
    if envelope.event_type == _COMMERCIAL:
        return CommercialChangedEvent(
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
            product_id=envelope.aggregate_id,
            sku=envelope.sku,
            aggregate_version=version,
            changed_fields=tuple(data.get("changed_fields", ())),
            price=Decimal(data["price"]["amount"]),
            cost=Decimal(data["cost"]["amount"]),
            currency=data["price"]["currency"],
            stock=int(data["stock"]),
            supplier=data["supplier"],
        )
    if envelope.event_type == _DELETED:
        return ProductDeletedEvent(
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
            product_id=envelope.aggregate_id,
            sku=envelope.sku,
            aggregate_version=version,
        )
    raise EventValidationError(
        f"неизвестный тип события: {envelope.event_type}"
    )


def _snapshot(data: dict, version: int) -> ProductSnapshot:
    metrics = data["metrics"]
    source = data.get("source_updated_at")
    return ProductSnapshot(
        product_id=UUID(data["product_id"]),
        sku=data["sku"],
        name=data["name"],
        description=data["description"],
        category=data["category"],
        brand=data["brand"],
        supplier=data["supplier"],
        price=Decimal(data["price"]["amount"]),
        cost=Decimal(data["cost"]["amount"]),
        currency=data["price"]["currency"],
        stock=int(data["stock"]),
        sales_per_month=int(metrics["sales_per_month"]),
        avg_rating=Decimal(metrics["avg_rating"]),
        review_count=int(metrics["review_count"]),
        source_updated_at=date.fromisoformat(source) if source else None,
        aggregate_version=version,
    )
