"""DTO ``OutboxMessage`` — строка transactional outbox (вход порта).

Собирается в application из ``EmbeddingRequest`` (готовый конверт команды
``embedding.documents.requested.v1``). Инфраструктура персистит её как есть;
relay публикует ``payload`` в exchange ``embedding.jobs``.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """Сообщение outbox (self-contained конверт команды).

    Attributes:
        id: Message-id (uuidv7).
        aggregate_type: Тип агрегата (``"embedding_request"``).
        aggregate_id: Идентификатор агрегата (= ``request_id``).
        event_type: Тип события = routing key команды.
        payload: Полный конверт команды (JSON-совместимый dict).
        occurred_at: Доменное время постановки команды.
        headers: Заголовки брокера (message_id/trace_id/...).
    """

    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    headers: dict[str, Any] = field(default_factory=dict)
