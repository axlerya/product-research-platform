"""Маппинг доменных событий в ``OutboxMessage`` (сборка конверта).

Живёт в прикладном слое (не в инфраструктуре): это чистое преобразование
доменного события и состояния товара в JSON-совместимый конверт. Деньги и
рейтинг сериализуются строкой (без потери точности). На проводе
``event_version`` — semver-строка ``"1.0"``; в колонке outbox — MAJOR (int).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from catalog_service.application.outbox_message import OutboxMessage
from catalog_service.application.ports.services import IdGenerator
from catalog_service.domain.entities.product import Product
from catalog_service.domain.events import (
    DomainEvent,
    ProductCommercialDataChanged,
    ProductContentChanged,
    ProductCreated,
    ProductDeleted,
)
from catalog_service.domain.value_objects.money import Money

_PRODUCER = "catalog-service"
_EVENT_VERSION_WIRE = "1.0"
_EVENT_VERSION_MAJOR = 1


def _money(value: Money) -> dict[str, str]:
    """Сериализует деньги как ``{amount, currency}`` строками."""
    return {"amount": f"{value.amount:.2f}", "currency": value.currency.code}


def _build_data(event: DomainEvent, product: Product) -> dict[str, Any]:
    """Строит тело ``data`` события по его типу."""
    product_id = str(product.id.value)
    sku = product.sku.value
    if isinstance(event, ProductCreated):
        return {
            "product_id": product_id,
            "sku": sku,
            "name": product.name,
            "description": product.description,
            "category": product.category.name,
            "brand": product.brand.name,
            "supplier": product.supplier.name,
            "price": _money(product.pricing.price),
            "cost": _money(product.pricing.cost),
            "stock": product.stock.quantity,
            "metrics": {
                "sales_per_month": product.metrics.sales_per_month,
                "avg_rating": f"{product.metrics.avg_rating.value:.2f}",
                "review_count": product.metrics.review_count,
            },
            "source_updated_at": (
                product.source_updated_at.isoformat()
                if product.source_updated_at is not None
                else None
            ),
        }
    if isinstance(event, ProductContentChanged):
        return {
            "product_id": product_id,
            "sku": sku,
            "changed_fields": list(event.changed_fields),
            "name": product.name,
            "description": product.description,
            "category": product.category.name,
            "brand": product.brand.name,
        }
    if isinstance(event, ProductCommercialDataChanged):
        return {
            "product_id": product_id,
            "sku": sku,
            "changed_fields": list(event.changed_fields),
            "price": _money(product.pricing.price),
            "cost": _money(product.pricing.cost),
            "stock": product.stock.quantity,
            "supplier": product.supplier.name,
        }
    if isinstance(event, ProductDeleted):
        return {"product_id": product_id, "sku": sku}
    raise ValueError(f"Неизвестное событие: {type(event).__name__}")


def build_outbox_message(
    event: DomainEvent, product: Product, *, message_id: UUID
) -> OutboxMessage:
    """Собирает ``OutboxMessage`` из события и состояния товара.

    Args:
        event: Доменное событие.
        product: Товар ПОСЛЕ мутации (несёт актуальную версию).
        message_id: Идентификатор сообщения (uuidv7).

    Returns:
        Готовая строка outbox с self-contained конвертом в ``payload``.
    """
    envelope = {
        "event_id": str(message_id),
        "event_type": event.routing_key,
        "event_version": _EVENT_VERSION_WIRE,
        "aggregate_type": "product",
        "aggregate_id": str(product.id.value),
        "sku": product.sku.value,
        "aggregate_version": product.version,
        "occurred_at": event.occurred_at.isoformat(),
        "producer": _PRODUCER,
        "data": _build_data(event, product),
    }
    return OutboxMessage(
        id=message_id,
        aggregate_type="product",
        aggregate_id=product.id.value,
        event_type=event.routing_key,
        event_version=_EVENT_VERSION_MAJOR,
        aggregate_version=product.version,
        payload=envelope,
        occurred_at=event.occurred_at,
    )


def build_messages(
    events: Sequence[DomainEvent], product: Product, id_gen: IdGenerator
) -> list[OutboxMessage]:
    """Строит строки outbox для набора событий одной команды."""
    return [
        build_outbox_message(event, product, message_id=id_gen.new_message_id())
        for event in events
    ]
