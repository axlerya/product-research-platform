"""Порт EventPublisher — публикация события в брокер (только relay)."""

from collections.abc import Mapping
from typing import Protocol


class EventPublisher(Protocol):
    """Публикация подтверждённого события в брокер."""

    async def publish(
        self,
        payload: Mapping[str, object],
        *,
        routing_key: str,
        message_id: str,
        headers: Mapping[str, str],
    ) -> None:
        """Публикует конверт с publisher confirm."""
        ...
