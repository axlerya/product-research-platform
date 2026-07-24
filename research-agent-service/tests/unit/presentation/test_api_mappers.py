"""Тесты мапперов домен/DTO → схемы ответа."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from research_agent_service.application.dto.answer import AnswerQueryResult
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    Confidence,
    ErrorCategory,
    ErrorCode,
    RunStage,
    RunStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)
from research_agent_service.domain.value_objects.run_error import RunError
from research_agent_service.domain.value_objects.usage import TokenUsage
from research_agent_service.presentation.schemas.mappers import (
    answer_result_to_response,
    run_to_detail,
    run_to_summary,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _run() -> AgentRun:
    return AgentRun(
        id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        query_message_id=MessageId(UUID(int=3)),
        model="qwen3",
        prompt_version="v1",
        started_at=_NOW,
    )


def test_answer_result_to_response() -> None:
    """Результат use case → тело ответа со строковым score."""
    result = AnswerQueryResult(
        agent_run_id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        status=RunStatus.DEGRADED,
        answer="ответ",
        citations=(
            Citation(
                source_type=CitationType.PRODUCT,
                ref="SKU-1",
                title="Наушники",
                snippet="s",
                position=0,
                retrieved_at=_NOW,
                score=Decimal("0.91"),
            ),
        ),
        used_tools=(ToolName.PRODUCT_CATALOG_RAG,),
        confidence=Confidence.MEDIUM,
        degradations=(Degradation("reranker", "unavailable"),),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        latency_ms=1234,
    )

    response = answer_result_to_response(result)

    assert response.agent_run_id == UUID(int=1)
    assert response.status is RunStatus.DEGRADED
    assert response.used_tools == ["product_catalog_rag"]
    assert response.citations[0].score == "0.91"
    assert response.usage.total_tokens == 15
    assert response.degradations[0].dependency == "reranker"
    assert response.latency_ms == 1234


def test_run_to_summary() -> None:
    """Завершённый прогон → краткая карточка."""
    run = _run()
    run.complete(
        answer_message_id=MessageId(UUID(int=4)),
        usage=TokenUsage(prompt_tokens=7, completion_tokens=3),
        confidence=Confidence.HIGH,
        degradations=(),
        loop_steps=2,
        now=_NOW,
    )

    summary = run_to_summary(run)

    assert summary.agent_run_id == UUID(int=1)
    assert summary.status is RunStatus.COMPLETED
    assert summary.confidence is Confidence.HIGH
    assert summary.finished_at == _NOW


def test_run_to_detail_with_error() -> None:
    """Провалившийся прогон → детали с кодом ошибки."""
    run = _run()
    run.fail(
        error=RunError(
            code=ErrorCode.INTERNAL,
            category=ErrorCategory.INTERNAL,
            stage=RunStage.PLAN,
            message="boom",
        ),
        now=_NOW,
    )

    detail = run_to_detail(run)

    assert detail.status is RunStatus.FAILED
    assert detail.error_code == "internal"
    assert detail.loop_steps == 0
    assert detail.usage.total_tokens == 0


def test_run_to_detail_without_error() -> None:
    """Успешный прогон → error_code отсутствует."""
    run = _run()
    run.complete(
        answer_message_id=MessageId(UUID(int=4)),
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        confidence=Confidence.HIGH,
        degradations=(),
        loop_steps=1,
        now=_NOW,
    )

    assert run_to_detail(run).error_code is None
