"""DTO ``OutboxMessage`` — строка transactional outbox (вход порта).

Собирается в прикладном слое из доменного события и состояния товара
(см. ``event_mapping``). Инфраструктура лишь персистит её как есть.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """Сообщение outbox (self-contained конверт события).

    Attributes:
        id: Message-id (uuidv7) — ключ идемпотентности консюмера.
        aggregate_type: Тип агрегата (``"product"``).
        aggregate_id: Идентификатор агрегата.
        event_type: Тип события = routing key.
        event_version: MAJOR версии схемы (в payload — semver-строка).
        aggregate_version: Версия товара ПОСЛЕ изменения.
        payload: Полный конверт события (JSON-совместимый dict).
        occurred_at: Доменное время события.
    """

    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    event_version: int
    aggregate_version: int
    payload: dict[str, Any]
    occurred_at: datetime
