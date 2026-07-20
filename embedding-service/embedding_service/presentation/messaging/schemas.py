"""Pydantic tolerant-reader конверта команды (§5.5).

``extra="ignore"`` — незнакомые поля MINOR-эволюции продюсера молча
игнорируются. Только presentation знает про Pydantic.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestedItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text_id: str
    text: str


class RequestedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_id: UUID
    model: str | None = None
    return_dense: bool
    return_sparse: bool
    items: list[RequestedItem] = Field(min_length=1)


class RequestedEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    event_id: UUID
    event_type: str
    event_version: str = "1.0"
    aggregate_type: str = "embedding_job"
    occurred_at: datetime
    producer: str
    trace_id: str | None = None
    correlation_id: str | None = None
    data: RequestedData
