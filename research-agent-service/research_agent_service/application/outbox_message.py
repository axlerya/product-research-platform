"""OutboxMessage — запись transactional outbox (application-слой)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """Одно событие для надёжной публикации через outbox-relay.

    ``id`` == event_id == broker message_id (uuidv7). ``payload`` — полный
    конверт события. ``headers`` несут trace_id/correlation_id для relay.
    """

    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    payload: Mapping[str, object]
    occurred_at: datetime
    headers: Mapping[str, str] = field(default_factory=dict)
    next_attempt_at: datetime | None = None
