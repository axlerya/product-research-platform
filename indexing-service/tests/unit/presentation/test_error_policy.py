"""Тесты политики ack/retry/DLQ консюмера (§7.4)."""

from datetime import UTC, datetime
from uuid import UUID

from indexing_service.application.exceptions import (
    ProductNotInCatalog,
    VectorIndexError,
)
from indexing_service.presentation.messaging.error_policy import (
    death_count,
    dispatch,
)
from indexing_service.presentation.messaging.schemas import CatalogEnvelope

NOW = datetime(2026, 7, 19, tzinfo=UTC)
PID = UUID(int=1)

_CREATED_DATA = {
    "product_id": str(PID),
    "sku": "PROD-001",
    "name": "N",
    "description": "D",
    "category": "C",
    "brand": "B",
    "supplier": "S",
    "price": {"amount": "10.00", "currency": "RUB"},
    "cost": {"amount": "4.00", "currency": "RUB"},
    "stock": 5,
    "metrics": {"sales_per_month": 1, "avg_rating": "4.00", "review_count": 2},
    "source_updated_at": None,
}


def _valid_envelope() -> CatalogEnvelope:
    return CatalogEnvelope(
        event_id=UUID(int=2),
        event_type="catalog.product.created",
        aggregate_id=PID,
        sku="PROD-001",
        aggregate_version=1,
        occurred_at=NOW,
        data=_CREATED_DATA,
    )


def _bad_envelope() -> CatalogEnvelope:
    return CatalogEnvelope(
        event_id=UUID(int=3),
        event_type="catalog.product.unknown",
        aggregate_id=PID,
        sku="PROD-001",
        aggregate_version=1,
        occurred_at=NOW,
        data={},
    )


class FakeMessage:
    def __init__(self, headers=None) -> None:
        self.headers = headers or {}
        self.acked = False
        self.rejected = False

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool = False) -> None:
        self.rejected = True


class FakeUseCase:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.calls = 0

    async def handle(self, event):
        self.calls += 1
        if self._error is not None:
            raise self._error


class Parker:
    def __init__(self) -> None:
        self.parked: list = []

    async def __call__(self, message) -> None:
        self.parked.append(message)


def test_death_count():
    assert death_count({}) == 0
    assert death_count({"x-death": [{"count": 3}]}) == 3


async def test_success_acks():
    message, parker = FakeMessage(), Parker()
    await dispatch(
        _valid_envelope(),
        message,
        use_case=FakeUseCase(),
        park=parker,
        max_attempts=5,
    )
    assert message.acked is True
    assert parker.parked == []


async def test_permanent_error_parks_and_acks():
    message, parker = FakeMessage(), Parker()
    await dispatch(
        _valid_envelope(),
        message,
        use_case=FakeUseCase(ProductNotInCatalog("нет")),
        park=parker,
        max_attempts=5,
    )
    assert parker.parked == [message]
    assert message.acked is True


async def test_parse_poison_parks():
    message, parker = FakeMessage(), Parker()
    used = FakeUseCase()
    await dispatch(
        _bad_envelope(),
        message,
        use_case=used,
        park=parker,
        max_attempts=5,
    )
    assert used.calls == 0
    assert parker.parked == [message]
    assert message.acked is True


async def test_transient_error_rejects_for_retry():
    message, parker = FakeMessage(), Parker()
    await dispatch(
        _valid_envelope(),
        message,
        use_case=FakeUseCase(VectorIndexError("qdrant down")),
        park=parker,
        max_attempts=5,
    )
    assert message.rejected is True
    assert message.acked is False
    assert parker.parked == []


async def test_transient_error_parks_when_exhausted():
    message = FakeMessage(headers={"x-death": [{"count": 5}]})
    parker = Parker()
    await dispatch(
        _valid_envelope(),
        message,
        use_case=FakeUseCase(VectorIndexError("qdrant down")),
        park=parker,
        max_attempts=5,
    )
    assert parker.parked == [message]
    assert message.acked is True
    assert message.rejected is False
