"""Порт ``OutboxRepository`` — запись команд в transactional outbox."""

from collections.abc import Sequence
from typing import Protocol

from indexing_service.application.outbox_message import OutboxMessage


class OutboxRepository(Protocol):
    """Пишет сообщения outbox в текущую транзакцию UoW."""

    async def add_many(self, messages: Sequence[OutboxMessage]) -> None:
        """Добавляет сообщения outbox (чистый INSERT в сессию)."""
        ...
