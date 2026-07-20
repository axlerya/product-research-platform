"""Политика ack/retry/DLQ консюмера документов (§5.7, D14).

Инвариант: ack входящей команды — ТОЛЬКО после подтверждённой публикации
результата (ack-после-confirm, §5.8, D9). Идемпотентность (§5.6) делает
ретраи безопасными. Битая схема → park (poison, не hot-loop).
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from embedding_service.application.dto import DocumentsGenerated
from embedding_service.application.exceptions import (
    PermanentError,
    TransientError,
)
from embedding_service.presentation.messaging.parsing import to_command
from embedding_service.presentation.messaging.schemas import RequestedEnvelope


class _Message(Protocol):
    headers: Mapping[str, Any]

    async def ack(self) -> None: ...
    async def reject(self, requeue: bool = False) -> None: ...


class _UseCase(Protocol):
    async def handle(self, command: Any) -> DocumentsGenerated: ...


_Publish = Callable[[RequestedEnvelope, DocumentsGenerated], Awaitable[None]]
_Park = Callable[[_Message], Awaitable[None]]


def death_count(headers: Mapping[str, Any]) -> int:
    """Число прошлых доставок из заголовка ``x-death``."""
    deaths = headers.get("x-death") or []
    if not deaths:
        return 0
    return int(deaths[0].get("count", 0))


async def dispatch(
    payload: Mapping[str, Any],
    message: _Message,
    *,
    use_case: _UseCase,
    publish: _Publish,
    park: _Park,
    max_attempts: int,
) -> None:
    """Обрабатывает команду и решает ack/reject/park.

    - битая схема → ``park`` + ``ack`` (poison)
    - успех → ``publish`` (confirm) → ``ack`` (строго в этом порядке)
    - ``PermanentError`` → ``park`` + ``ack``
    - ``TransientError`` → ``reject`` (retry-лестница) или ``park`` при
      исчерпании ``max_attempts``
    """
    try:
        envelope = RequestedEnvelope.model_validate(payload)
        command = to_command(envelope)
    except ValidationError:
        await park(message)
        await message.ack()
        return
    try:
        result = await use_case.handle(command)
        await publish(envelope, result)
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
