"""SQLAlchemy-репозиторий transactional outbox."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.infrastructure.db.mappers import outbox_to_orm


class SqlAlchemyOutboxRepository:
    """Вставка исходящих событий в текущую сессию (без брокера)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, messages: Sequence[OutboxMessage]) -> None:
        now = datetime.now(UTC)
        for message in messages:
            self._session.add(outbox_to_orm(message, created_at=now))
