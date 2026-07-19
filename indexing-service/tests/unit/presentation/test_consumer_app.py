"""In-memory тест consumer-app через ``TestRabbitBroker`` (без Docker)."""

from datetime import UTC, datetime
from uuid import UUID

from faststream.rabbit import TestRabbitBroker

from indexing_service.domain.services.change_classifier import IndexingAction
from indexing_service.presentation.messaging.consumer_app import broker
from indexing_service.presentation.messaging.topology import CATALOG_EXCHANGE

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
PID = UUID(int=1)

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


def _envelope(event_type: str, data: dict) -> dict:
    return {
        "event_id": str(UUID(int=2)),
        "event_type": event_type,
        "aggregate_id": str(PID),
        "sku": "PROD-001",
        "aggregate_version": 1,
        "occurred_at": NOW.isoformat(),
        "data": data,
    }


class FakeUseCase:
    def __init__(self) -> None:
        self.events: list = []

    async def handle(self, event):
        self.events.append(event)
        return IndexingAction.FULL_INDEX


class FakeParker:
    def __init__(self) -> None:
        self.parked: list = []

    async def __call__(self, message) -> None:
        self.parked.append(message)


def _wire(test_broker, use_case, parker):
    test_broker.context.set_global("use_case", use_case)
    test_broker.context.set_global("parker", parker)
    test_broker.context.set_global("max_attempts", 5)


async def test_created_routes_to_use_case():
    fake, parker = FakeUseCase(), FakeParker()
    async with TestRabbitBroker(broker) as test_broker:
        _wire(test_broker, fake, parker)
        await test_broker.publish(
            _envelope("catalog.product.created", _CREATED_DATA),
            exchange=CATALOG_EXCHANGE,
            routing_key="catalog.product.created",
        )
    assert len(fake.events) == 1
    assert parker.parked == []


async def test_poison_event_parks_not_handled():
    fake, parker = FakeUseCase(), FakeParker()
    async with TestRabbitBroker(broker) as test_broker:
        _wire(test_broker, fake, parker)
        await test_broker.publish(
            _envelope("catalog.product.unknown", {}),
            exchange=CATALOG_EXCHANGE,
            routing_key="catalog.product.unknown",
        )
    assert fake.events == []
    assert len(parker.parked) == 1
