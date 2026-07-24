"""Тесты сущности AgentRun — жизненного цикла прогона."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.exceptions import (
    DomainError,
    RunAlreadyFinalized,
)
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    ErrorCategory,
    ErrorCode,
    RunStage,
    RunStatus,
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
    ToolCallId,
)
from research_agent_service.domain.value_objects.run_error import RunError
from research_agent_service.domain.value_objects.usage import TokenUsage

_STARTED = datetime(2026, 1, 1, tzinfo=UTC)
_FINISHED = datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC)


def _run() -> AgentRun:
    """Свежий прогон в состоянии RUNNING."""
    return AgentRun(
        id=AgentRunId.new(),
        conversation_id=ConversationId.new(),
        query_message_id=MessageId.new(),
        model="claude-opus-4-8",
        prompt_version="v1",
        started_at=_STARTED,
    )


def _tool_call(run: AgentRun, step: int) -> ToolCall:
    """Успешный вызов инструмента для прогона."""
    return ToolCall(
        id=ToolCallId.new(),
        agent_run_id=run.id,
        step_index=step,
        tool=ToolName.PRODUCT_CATALOG_RAG,
        status=ToolCallStatus.OK,
        started_at=_STARTED,
        finished_at=_FINISHED,
        latency_ms=100,
    )


def _complete(run: AgentRun, degradations: Sequence[Degradation] = ()) -> None:
    """Завершает прогон успехом с типовыми значениями."""
    run.complete(
        answer_message_id=MessageId.new(),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        confidence=Confidence.HIGH,
        degradations=tuple(degradations),
        loop_steps=3,
        now=_FINISHED,
    )


def _error() -> RunError:
    """Типовая ошибка прогона."""
    return RunError(
        code=ErrorCode.LLM_UNAVAILABLE,
        category=ErrorCategory.UPSTREAM,
        stage=RunStage.PLAN,
        message="провайдер LLM недоступен",
    )


def test_new_run_is_running_and_empty() -> None:
    """Новый прогон RUNNING, без вызовов, без ошибки и завершения."""
    run = _run()

    assert run.status is RunStatus.RUNNING
    assert run.tool_call_count == 0
    assert run.finished_at is None
    assert run.usage.total == 0
    assert run.degradations == ()
    assert run.error is None


def test_record_tool_call_appends() -> None:
    """record_tool_call накапливает вызовы, счётчик растёт."""
    run = _run()

    run.record_tool_call(_tool_call(run, 0))
    run.record_tool_call(_tool_call(run, 1))

    assert run.tool_call_count == 2


def test_complete_without_degradations_marks_completed() -> None:
    """Успешное завершение без деградаций → COMPLETED."""
    run = _run()

    _complete(run)

    assert run.status is RunStatus.COMPLETED
    assert run.confidence is Confidence.HIGH
    assert run.usage.total == 150
    assert run.loop_steps == 3
    assert run.finished_at == _FINISHED
    assert run.answer_message_id is not None


def test_complete_with_degradations_marks_degraded() -> None:
    """Завершение с деградациями → DEGRADED."""
    run = _run()

    _complete(run, degradations=(Degradation("reranker", "unimplemented"),))

    assert run.status is RunStatus.DEGRADED
    assert run.degradations[0].dependency == "reranker"


def test_fail_marks_failed_with_error() -> None:
    """fail переводит прогон в FAILED и сохраняет ошибку."""
    run = _run()
    error = _error()

    run.fail(error=error, now=_FINISHED)

    assert run.status is RunStatus.FAILED
    assert run.error is error
    assert run.finished_at == _FINISHED


def test_cannot_complete_twice() -> None:
    """Повторная финализация запрещена (INV: терминальный статус неизменяем)."""
    run = _run()
    _complete(run)

    with pytest.raises(RunAlreadyFinalized):
        _complete(run)


def test_cannot_fail_after_completion() -> None:
    """Нельзя провалить уже завершённый прогон."""
    run = _run()
    _complete(run)

    with pytest.raises(RunAlreadyFinalized):
        run.fail(error=_error(), now=_FINISHED)


def test_cannot_record_tool_call_after_finalization() -> None:
    """Нельзя добавить вызов инструмента в завершённый прогон."""
    run = _run()
    _complete(run)

    with pytest.raises(RunAlreadyFinalized):
        run.record_tool_call(_tool_call(run, 0))


def test_run_already_finalized_is_domain_error() -> None:
    """RunAlreadyFinalized — доменное исключение."""
    assert issubclass(RunAlreadyFinalized, DomainError)
