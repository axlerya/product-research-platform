"""Схема конверта события embedding-service — tolerant reader (§7)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmbeddingEventEnvelope(BaseModel):
    """Конверт события ``embedding.*``.

    Незнакомые поля игнорируются (``extra="ignore"``) — additive MINOR-
    эволюция контракта embedding-service не ломает наш консюмер.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: UUID
    event_type: str
    aggregate_id: UUID
    occurred_at: datetime
    data: dict[str, Any]
