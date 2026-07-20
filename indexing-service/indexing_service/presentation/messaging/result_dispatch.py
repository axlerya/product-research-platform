"""Политика ack/retry/DLQ консюмера результатов эмбеддинга (§7.4, §10).

Та же семантика, что у консюмера каталога: poison (``PermanentError`` —
битый контракт, dim/text_id, неизвестный код) → park сразу; временные
(``TransientError`` — сбой Qdrant) → reject в retry-лестницу, при исчерпании
попыток → park. Идемпотентность ``ApplyEmbeddingResult`` делает ретраи
безопасными.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from indexing_service.application.exceptions import (
    PermanentError,
    TransientError,
)
from indexing_service.presentation.messaging.embedding_parsing import (
    parse_embedding_result,
)
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)
from indexing_service.presentation.messaging.error_policy import death_count


class _Message(Protocol):
    headers: Mapping[str, Any]

    async def ack(self) -> None: ...
    async def reject(self, requeue: bool = False) -> None: ...


class _Handler(Protocol):
    async def handle(self, result: Any) -> Any: ...


async def dispatch_result(
    envelope: EmbeddingEventEnvelope,
    message: _Message,
    *,
    use_case: _Handler,
    park: Callable[[_Message], Awaitable[None]],
    max_attempts: int,
) -> None:
    """Обрабатывает событие-результат и решает ack/reject/park."""
    try:
        await use_case.handle(parse_embedding_result(envelope))
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
