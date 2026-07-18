"""Реализация ``OutboxRepository`` поверх SQLAlchemy."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.application.outbox_message import OutboxMessage
from catalog_service.infrastructure.db.models import OutboxORM


class SqlAlchemyOutboxRepository:
    """Записывает сообщения outbox в текущую сессию/транзакцию."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, messages: Sequence[OutboxMessage]) -> None:
        if not messages:
            return
        self._session.add_all(
            [
                OutboxORM(
                    id=message.id,
                    aggregate_type=message.aggregate_type,
                    aggregate_id=message.aggregate_id,
                    event_type=message.event_type,
                    event_version=message.event_version,
                    aggregate_version=message.aggregate_version,
                    payload=message.payload,
                    occurred_at=message.occurred_at,
                )
                for message in messages
            ]
        )
        await self._session.flush()
