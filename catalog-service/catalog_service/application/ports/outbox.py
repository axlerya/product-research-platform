"""Порт репозитория outbox."""

from collections.abc import Sequence
from typing import Protocol

from catalog_service.application.outbox_message import OutboxMessage


class OutboxRepository(Protocol):
    """Запись сообщений в outbox в рамках текущей транзакции UoW."""

    async def add_many(self, messages: Sequence[OutboxMessage]) -> None:
        """Добавляет сообщения outbox (в той же транзакции, что и агрегат)."""
        ...
