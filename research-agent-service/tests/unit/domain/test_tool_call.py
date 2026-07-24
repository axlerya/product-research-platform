"""Тесты сущности ToolCall."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.enums import (
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ToolCallId,
)

_STARTED = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
_FINISHED = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)


def _tool_call(**overrides: object) -> ToolCall:
    """Собирает валидный ToolCall с точечными переопределениями."""
    fields: dict[str, object] = {
        "id": ToolCallId.new(),
        "agent_run_id": AgentRunId.new(),
        "step_index": 0,
        "tool": ToolName.PRODUCT_CATALOG_RAG,
        "status": ToolCallStatus.OK,
        "started_at": _STARTED,
        "finished_at": _FINISHED,
        "latency_ms": 1000,
    }
    fields.update(overrides)
    return ToolCall(**fields)  # type: ignore[arg-type]


def test_tool_call_holds_fields_and_defaults() -> None:
    """Обязательные поля сохраняются; коллекции пусты по умолчанию."""
    call = _tool_call()

    assert call.tool is ToolName.PRODUCT_CATALOG_RAG
    assert call.status is ToolCallStatus.OK
    assert call.latency_ms == 1000
    assert call.arguments == {}
    assert call.result_summary == {}
    assert call.provenance == ()
    assert call.error is None


def test_tool_call_carries_arguments_and_error() -> None:
    """Аргументы и ошибка сохраняются."""
    call = _tool_call(
        status=ToolCallStatus.ERROR,
        arguments={"query": "наушники"},
        error="upstream unavailable",
    )

    assert call.arguments == {"query": "наушники"}
    assert call.error == "upstream unavailable"


def test_tool_call_is_frozen() -> None:
    """ToolCall неизменяем."""
    call = _tool_call()

    with pytest.raises(FrozenInstanceError):
        call.status = ToolCallStatus.TIMEOUT
