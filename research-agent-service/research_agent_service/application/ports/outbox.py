"""Порт OutboxRepository — запись событий в transactional outbox."""

from collections.abc import Sequence
from typing import Protocol

from research_agent_service.application.outbox_message import OutboxMessage


class OutboxRepository(Protocol):
    """Вставка исходящих событий в той же транзакции, что и мутация."""

    async def add_many(self, messages: Sequence[OutboxMessage]) -> None:
        """Добавляет события в outbox (без обращения к брокеру)."""
        ...
