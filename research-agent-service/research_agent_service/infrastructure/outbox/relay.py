"""OutboxPublisher — relay: публикация событий из outbox в брокер.

Отдельный процесс от write-path: выбирает неопубликованные строки
FOR UPDATE SKIP LOCKED, публикует через EventPublisher (с publisher
confirms), помечает published_at. На ошибке — экспоненциальный бэкофф с
джиттером; после исчерпания попыток строка уходит в карантин (failed_at).
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from research_agent_service.application.ports.publisher import EventPublisher
from research_agent_service.infrastructure.db.models import OutboxEventORM

_BACKOFF_CAP_S = 300
_LAST_ERROR_MAX = 1000


class OutboxPublisher:
    """Дренаж outbox с надёжной публикацией."""

    def __init__(
        self,
        *,
        publisher: EventPublisher,
        batch_size: int = 100,
        max_attempts: int = 10,
    ) -> None:
        self._publisher = publisher
        self._batch_size = batch_size
        self._max_attempts = max_attempts

    async def drain_batch(self, session: AsyncSession) -> int:
        """Публикует одну партию; возвращает число опубликованных строк."""
        now = datetime.now(UTC)
        stmt = (
            select(OutboxEventORM)
            .where(
                OutboxEventORM.published_at.is_(None),
                OutboxEventORM.failed_at.is_(None),
                OutboxEventORM.attempts < self._max_attempts,
                or_(
                    OutboxEventORM.next_attempt_at.is_(None),
                    OutboxEventORM.next_attempt_at <= now,
                ),
            )
            .order_by(OutboxEventORM.id)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = (await session.scalars(stmt)).all()
        published = 0
        for row in rows:
            if await self._try_publish(row, now):
                published += 1
        await session.commit()
        return published

    async def drain_all(self, session: AsyncSession) -> int:
        """Дренирует, пока партии непустые; возвращает общее число."""
        total = 0
        while True:
            count = await self.drain_batch(session)
            total += count
            if count == 0:
                return total

    async def _try_publish(self, row: OutboxEventORM, now: datetime) -> bool:
        try:
            await self._publisher.publish(
                row.payload,
                routing_key=row.event_type,
                message_id=str(row.id),
                headers={str(k): str(v) for k, v in row.headers.items()},
            )
        except Exception as exc:
            self._mark_failed(row, now, str(exc))
            return False
        row.published_at = now
        return True

    def _mark_failed(
        self, row: OutboxEventORM, now: datetime, error: str
    ) -> None:
        row.attempts += 1
        row.last_error = error[:_LAST_ERROR_MAX]
        if row.attempts >= self._max_attempts:
            row.failed_at = now
            return
        backoff = min(2**row.attempts, _BACKOFF_CAP_S)
        jitter = random.uniform(0, backoff * 0.1)
        row.next_attempt_at = now + timedelta(seconds=backoff + jitter)
