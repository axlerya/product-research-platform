"""Политика ack/retry/DLQ консюмера (§7.4).

Постоянные ошибки (poison) паркуются сразу; временные — reject в retry-
лестницу, а при исчерпании попыток паркуются. Идемпотентность (§6) делает
ретраи безопасными.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from indexing_service.application.exceptions import (
    PermanentError,
    TransientError,
)
from indexing_service.presentation.messaging.parsing import parse_event
from indexing_service.presentation.messaging.schemas import CatalogEnvelope


class _Message(Protocol):
    """Утиный тип ``RabbitMessage`` для policy."""

    headers: Mapping[str, Any]

    async def ack(self) -> None: ...
    async def reject(self, requeue: bool = False) -> None: ...


class _Handler(Protocol):
    async def handle(self, event: Any) -> Any: ...


def death_count(headers: Mapping[str, Any]) -> int:
    """Число прошлых доставок из заголовка ``x-death``."""
    deaths = headers.get("x-death") or []
    if not deaths:
        return 0
    return int(deaths[0].get("count", 0))


async def dispatch(
    envelope: CatalogEnvelope,
    message: _Message,
    *,
    use_case: _Handler,
    park: Callable[[_Message], Awaitable[None]],
    max_attempts: int,
) -> None:
    """Обрабатывает сообщение и решает ack/reject/park.

    - успех → ``ack``
    - ``PermanentError`` → ``park`` + ``ack`` (poison, §7.1)
    - ``TransientError`` → ``reject`` (retry-лестница) или ``park`` при
      исчерпании ``max_attempts``
    """
    try:
        await use_case.handle(parse_event(envelope))
        await message.ack()
    except PermanentError:
        await park(message)
        await message.ack()
    except TransientError:
        if death_count(message.headers) >= max_attempts:
            await park(message)
            await message.ack()
        else:
            await message.reject(requeue=False)
