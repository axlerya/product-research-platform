"""Схема конверта события каталога — tolerant reader (§3.3)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CatalogEnvelope(BaseModel):
    """Конверт события.

    Незнакомые поля игнорируются (``extra="ignore"``) — additive MINOR-
    эволюция контракта не требует изменений консюмера.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: UUID
    event_type: str
    aggregate_id: UUID
    sku: str
    aggregate_version: int = Field(ge=1)
    occurred_at: datetime
    data: dict[str, Any]
