"""Outbox relay: выборка pending-строк и публикация (at-least-once).

Выборка — ``FOR UPDATE SKIP LOCKED`` (несколько воркеров без двойной
публикации). Успех → ``published_at``; ошибка → инкремент ``attempts`` и
экспоненциальный backoff; исчерпание попыток → ``failed_at`` (карантин).
``payload`` уже self-contained конверт команды — публикуем как есть.
"""

from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from indexing_service.infrastructure.db.models import OutboxORM
from indexing_service.infrastructure.messaging.broker import EventPublisher

_BACKOFF_CAP_S = 300


class OutboxPublisher:
    """Публикует накопленные команды из outbox в брокер."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        publisher: EventPublisher,
        *,
        max_attempts: int = 10,
        batch_size: int = 100,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._publisher = publisher
        self._max_attempts = max_attempts
        self._batch_size = batch_size

    async def drain_batch(self) -> int:
        """Публикует один батч pending-строк. Возвращает число обработанных."""
        async with self._sessionmaker() as session, session.begin():
            stmt = (
                select(
                    OutboxORM.id,
                    OutboxORM.event_type,
                    OutboxORM.aggregate_id,
                    OutboxORM.payload,
                    OutboxORM.headers,
                    OutboxORM.attempts,
                )
                .where(
                    OutboxORM.published_at.is_(None),
                    OutboxORM.failed_at.is_(None),
                    OutboxORM.attempts < self._max_attempts,
                    or_(
                        OutboxORM.next_attempt_at.is_(None),
                        OutboxORM.next_attempt_at <= func.now(),
                    ),
                )
                .order_by(OutboxORM.id)
                .with_for_update(skip_locked=True)
                .limit(self._batch_size)
            )
            rows = (await session.execute(stmt)).all()
            if not rows:
                return 0
            published: list = []
            for row in rows:
                try:
                    await self._publisher.publish(
                        row.payload,
                        routing_key=row.event_type,
                        message_id=str(row.id),
                        headers={
                            **{k: str(v) for k, v in row.headers.items()},
                            "event_type": row.event_type,
                            "aggregate_id": str(row.aggregate_id),
                        },
                    )
                except Exception as exc:
                    await self._mark_failed(session, row, exc)
                else:
                    published.append(row.id)
            if published:
                await session.execute(
                    update(OutboxORM)
                    .where(OutboxORM.id.in_(published))
                    .values(published_at=func.now())
                )
            return len(rows)

    async def drain_all(self) -> int:
        """Публикует все доступные батчи, пока очередь не опустеет."""
        total = 0
        while (count := await self.drain_batch()) > 0:
            total += count
        return total

    async def _mark_failed(
        self, session: AsyncSession, row, exc: Exception
    ) -> None:
        attempts = row.attempts + 1
        values: dict = {"attempts": attempts, "last_error": str(exc)[:1000]}
        if attempts >= self._max_attempts:
            values["failed_at"] = func.now()
        else:
            backoff = min(2**attempts, _BACKOFF_CAP_S)
            values["next_attempt_at"] = func.now() + timedelta(seconds=backoff)
        await session.execute(
            update(OutboxORM).where(OutboxORM.id == row.id).values(**values)
        )
