"""Тесты event_mapping — конверты событий и записи outbox."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from research_agent_service.application.event_mapping import (
    EVENT_EVALUATION_REQUESTED,
    EVENT_FEEDBACK_RECEIVED,
    EVENT_QUERY_COMPLETED,
    EVENT_QUERY_FAILED,
    build_evaluation_requested_message,
    build_feedback_received_message,
    build_query_completed_message,
    build_query_failed_message,
)
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    Confidence,
    ErrorCategory,
    ErrorCode,
    FeedbackRating,
    RunStage,
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    FeedbackId,
    MessageId,
    ToolCallId,
)
from research_agent_service.domain.value_objects.run_error import RunError
from research_agent_service.domain.value_objects.usage import TokenUsage

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
_EVENT_ID = UUID(int=100)


def _run(*, trace_id: str | None, correlation_id: str | None) -> AgentRun:
    return AgentRun(
        id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        query_message_id=MessageId(UUID(int=3)),
        model="claude-opus-4-8",
        prompt_version="v1",
        started_at=_NOW,
        trace_id=trace_id,
        correlation_id=correlation_id,
    )


def _tool_call(run: AgentRun) -> ToolCall:
    return ToolCall(
        id=ToolCallId(UUID(int=7)),
        agent_run_id=run.id,
        step_index=0,
        tool=ToolName.PRODUCT_CATALOG_RAG,
        status=ToolCallStatus.OK,
        started_at=_NOW,
        finished_at=_NOW,
        latency_ms=100,
    )


def test_query_completed_envelope() -> None:
    """agent.query.completed.v1: конверт, data и headers заполнены."""
    run = _run(trace_id="trace-abc", correlation_id="corr-xyz")
    run.record_tool_call(_tool_call(run))
    run.complete(
        answer_message_id=MessageId(UUID(int=4)),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        confidence=Confidence.HIGH,
        degradations=(Degradation("reranker", "unavailable"),),
        loop_steps=3,
        now=_NOW,
    )
    citations = (
        Citation(
            source_type=CitationType.PRODUCT,
            ref="SKU-1",
            title="Наушники",
            snippet="описание",
            position=0,
            retrieved_at=_NOW,
            score=Decimal("0.9"),
        ),
    )

    msg = build_query_completed_message(
        run, citations, event_id=_EVENT_ID, query_hash="h", occurred_at=_NOW
    )
    env = msg.payload
    data = env["data"]

    assert msg.event_type == EVENT_QUERY_COMPLETED
    assert msg.id == _EVENT_ID
    assert msg.aggregate_type == "agent_run"
    assert msg.aggregate_id == UUID(int=1)
    assert env["event_version"] == "1.0"
    assert env["producer"] == "research-agent-service"
    assert env["event_id"] == str(_EVENT_ID)
    assert env["occurred_at"].endswith("Z")
    assert env["trace_id"] == "trace-abc"
    assert env["correlation_id"] == "corr-xyz"
    assert data["query_hash"] == "h"
    assert data["tools_used"] == ["product_catalog_rag"]
    assert data["confidence"] == "high"
    assert data["citations"][0]["ref"] == "SKU-1"
    assert data["degradations"][0]["dependency"] == "reranker"
    assert msg.headers["event_type"] == EVENT_QUERY_COMPLETED
    assert msg.headers["trace_id"] == "trace-abc"


def test_query_failed_envelope_omits_absent_trace() -> None:
    """agent.query.failed.v1: без trace/correlation они отсутствуют."""
    run = _run(trace_id=None, correlation_id=None)
    run.fail(
        error=RunError(
            code=ErrorCode.LLM_UNAVAILABLE,
            category=ErrorCategory.UPSTREAM,
            stage=RunStage.PLAN,
            message="провайдер недоступен",
        ),
        now=_NOW,
    )

    msg = build_query_failed_message(
        run, event_id=_EVENT_ID, query_hash="h", occurred_at=_NOW
    )
    env = msg.payload
    data = env["data"]

    assert msg.event_type == EVENT_QUERY_FAILED
    assert data["error_code"] == "llm_unavailable"
    assert data["error_category"] == "upstream"
    assert data["stage"] == "plan"
    assert "trace_id" not in env
    assert "trace_id" not in msg.headers


def test_feedback_received_envelope() -> None:
    """agent.feedback.received.v1: агрегат agent_feedback."""
    feedback = Feedback(
        id=FeedbackId(UUID(int=5)),
        agent_run_id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        rating=FeedbackRating.DOWN,
        created_at=_NOW,
        reason="неточные цены",
        labels=("pricing",),
    )

    msg = build_feedback_received_message(
        feedback, event_id=_EVENT_ID, occurred_at=_NOW
    )
    data = msg.payload["data"]

    assert msg.event_type == EVENT_FEEDBACK_RECEIVED
    assert msg.aggregate_type == "agent_feedback"
    assert msg.aggregate_id == UUID(int=5)
    assert data["rating"] == "down"
    assert data["labels"] == ["pricing"]


def test_evaluation_requested_envelope() -> None:
    """agent.evaluation.requested.v1: агрегат — логический evaluation_id."""
    msg = build_evaluation_requested_message(
        evaluation_id=UUID(int=9),
        agent_run_id=AgentRunId(UUID(int=1)),
        reason="negative_feedback",
        event_id=_EVENT_ID,
        occurred_at=_NOW,
    )
    data = msg.payload["data"]

    assert msg.event_type == EVENT_EVALUATION_REQUESTED
    assert msg.aggregate_type == "agent_evaluation"
    assert msg.aggregate_id == UUID(int=9)
    assert data["reason"] == "negative_feedback"
    assert data["agent_run_id"] == str(UUID(int=1))
