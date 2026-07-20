"""Integration: outbox-relay против реального Postgres (§7, §9).

Publisher — фейковый (плечо RabbitMQ проверяется отдельно): важна семантика
outbox — порядок, отметка published_at, backoff и карантин при сбоях.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from indexing_service.application.outbox_message import OutboxMessage
from indexing_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from indexing_service.infrastructure.outbox.relay import OutboxPublisher

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    async def publish(
        self,
        payload: dict[str, Any],
        *,
        routing_key: str,
        message_id: str,
        headers: dict[str, str],
    ) -> None:
        self.calls.append(
            {
                "payload": payload,
                "routing_key": routing_key,
                "message_id": message_id,
                "headers": headers,
            }
        )
        if self._fail:
            raise RuntimeError("broker down")


def _message(seq: int) -> OutboxMessage:
    request_id = uuid4()
    return OutboxMessage(
        id=UUID(int=seq),
        aggregate_type="embedding_request",
        aggregate_id=request_id,
        event_type="embedding.documents.requested.v1",
        payload={"data": {"request_id": str(request_id), "seq": seq}},
        occurred_at=_NOW,
        headers={"trace_id": f"trace-{seq}"},
    )


async def _seed(sessionmaker_, messages: list[OutboxMessage]) -> None:
    async with SqlAlchemyUnitOfWork(sessionmaker_) as uow:
        await uow.outbox.add_many(messages)
        await uow.commit()


async def _count(sessionmaker_, where: str) -> int:
    async with sessionmaker_() as session:
        return await session.scalar(
            text(f"SELECT count(*) FROM outbox WHERE {where}")
        )


async def test_drains_pending_in_id_order_and_marks_published(sessionmaker_):
    await _seed(sessionmaker_, [_message(1), _message(2), _message(3)])
    publisher = _FakePublisher()
    relay = OutboxPublisher(sessionmaker_, publisher)

    drained = await relay.drain_all()

    assert drained == 3
    assert [call["message_id"] for call in publisher.calls] == [
        str(UUID(int=1)),
        str(UUID(int=2)),
        str(UUID(int=3)),
    ]
    first = publisher.calls[0]
    assert first["routing_key"] == "embedding.documents.requested.v1"
    assert first["headers"]["trace_id"] == "trace-1"
    assert first["headers"]["event_type"] == "embedding.documents.requested.v1"
    assert await _count(sessionmaker_, "published_at IS NOT NULL") == 3
    assert await relay.drain_all() == 0


async def test_failure_backs_off_and_leaves_unpublished(sessionmaker_):
    await _seed(sessionmaker_, [_message(1)])
    relay = OutboxPublisher(sessionmaker_, _FakePublisher(fail=True))

    await relay.drain_batch()

    assert await _count(sessionmaker_, "published_at IS NULL") == 1
    assert await _count(sessionmaker_, "attempts = 1") == 1
    assert await _count(sessionmaker_, "next_attempt_at IS NOT NULL") == 1
    # backoff в будущем ⇒ строка не готова к повтору
    assert await relay.drain_batch() == 0


async def test_exhausted_attempts_are_quarantined(sessionmaker_):
    await _seed(sessionmaker_, [_message(1)])
    relay = OutboxPublisher(
        sessionmaker_, _FakePublisher(fail=True), max_attempts=1
    )

    await relay.drain_batch()

    assert await _count(sessionmaker_, "failed_at IS NOT NULL") == 1
    assert await _count(sessionmaker_, "published_at IS NULL") == 1
    assert await relay.drain_batch() == 0
