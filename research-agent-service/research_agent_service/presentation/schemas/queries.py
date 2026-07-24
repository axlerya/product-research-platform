"""Схемы GET /queries и GET /queries/{id}."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from research_agent_service.domain.value_objects.enums import (
    Confidence,
    RunStatus,
)
from research_agent_service.presentation.schemas.common import (
    DegradationSchema,
    UsageSchema,
)


class RunSummary(BaseModel):
    """Краткая карточка прогона для списка."""

    agent_run_id: UUID
    conversation_id: UUID
    status: RunStatus
    model: str
    confidence: Confidence | None
    tool_call_count: int
    started_at: datetime
    finished_at: datetime | None


class RunDetail(RunSummary):
    """Детали прогона (со сводкой токенов, деградациями, шагами)."""

    usage: UsageSchema
    degradations: list[DegradationSchema]
    loop_steps: int
    error_code: str | None


class QueryListResponse(BaseModel):
    """Страница списка прогонов."""

    items: list[RunSummary]
    limit: int
    offset: int
