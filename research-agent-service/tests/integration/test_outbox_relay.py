"""Интеграционные тесты relay outbox (PostgreSQL в контейнере)."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from research_agent_service.infrastructure.db.models import OutboxEventORM
from research_agent_service.infrastructure.outbox.relay import OutboxPublisher

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.published: list[str] = []
        self._fail = fail

    async def publish(
        self,
        payload: Mapping[str, object],
        *,
        routing_key: str,
        message_id: str,
        headers: Mapping[str, str],
    ) -> None:
        if self._fail:
            raise RuntimeError("nack")
        self.published.append(message_id)


def _event(n: int, *, attempts: int = 0) -> OutboxEventORM:
    return OutboxEventORM(
        id=UUID(int=n),
        aggregate_type="agent_run",
        aggregate_id=UUID(int=n),
        event_type="agent.query.completed.v1",
        payload={"n": n},
        headers={"trace_id": "t"},
        occurred_at=_NOW,
        created_at=_NOW,
        attempts=attempts,
    )


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    events: Iterable[OutboxEventORM],
) -> None:
    async with session_factory() as session:
        for event in events:
            session.add(event)
        await session.commit()


async def test_drain_publishes_and_marks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Дренаж публикует все строки и помечает published_at."""
    await _seed(session_factory, [_event(1), _event(2)])
    publisher = _FakePublisher()
    relay = OutboxPublisher(publisher=publisher)

    async with session_factory() as session:
        count = await relay.drain_all(session)

    assert count == 2
    assert len(publisher.published) == 2
    async with session_factory() as session:
        rows = (await session.scalars(select(OutboxEventORM))).all()
    assert all(row.published_at is not None for row in rows)


async def test_transient_failure_schedules_retry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ошибка публикации → попытка++ и назначен next_attempt_at."""
    await _seed(session_factory, [_event(3)])
    relay = OutboxPublisher(publisher=_FakePublisher(fail=True))

    async with session_factory() as session:
        count = await relay.drain_batch(session)

    assert count == 0
    async with session_factory() as session:
        row = await session.get(OutboxEventORM, UUID(int=3))
    assert row is not None
    assert row.published_at is None
    assert row.attempts == 1
    assert row.next_attempt_at is not None


async def test_quarantine_after_max_attempts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Исчерпание попыток → карантин (failed_at)."""
    await _seed(session_factory, [_event(4, attempts=9)])
    relay = OutboxPublisher(
        publisher=_FakePublisher(fail=True), max_attempts=10
    )

    async with session_factory() as session:
        await relay.drain_batch(session)

    async with session_factory() as session:
        row = await session.get(OutboxEventORM, UUID(int=4))
    assert row is not None
    assert row.attempts == 10
    assert row.failed_at is not None
