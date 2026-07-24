"""Сущность ToolCall — вызов инструмента внутри прогона."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import (
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ToolCallId,
)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Один вызов инструмента: аргументы, исход, провенанс, тайминги.

    Attributes:
        id: Идентификатор вызова.
        agent_run_id: Прогон, которому принадлежит вызов.
        step_index: Порядковый номер шага в прогоне.
        tool: Инструмент (из закрытого allowlist).
        status: Исход вызова.
        started_at: Начало вызова.
        finished_at: Завершение вызова.
        latency_ms: Длительность в миллисекундах.
        arguments: Провалидированные аргументы вызова.
        result_summary: Краткая сводка результата.
        provenance: Источники, полученные вызовом.
        error: Сообщение об ошибке, если вызов не удался.
    """

    id: ToolCallId
    agent_run_id: AgentRunId
    step_index: int
    tool: ToolName
    status: ToolCallStatus
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    arguments: Mapping[str, object] = field(default_factory=dict)
    result_summary: Mapping[str, object] = field(default_factory=dict)
    provenance: tuple[Citation, ...] = ()
    error: str | None = None
