"""Контрактные тесты конвертов событий: payload соответствует JSON Schema.

Схемы фиксируют проводной контракт для потребителей. additionalProperties
False ловит незадекларированный дрейф полей в билдерах событий.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from jsonschema import validate

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

pytestmark = pytest.mark.contract

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _envelope(event_type: str, data_schema: dict) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "event_id",
            "event_type",
            "event_version",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
            "producer",
            "data",
        ],
        "properties": {
            "event_id": {"type": "string"},
            "event_type": {"const": event_type},
            "event_version": {"const": "1.0"},
            "aggregate_type": {"type": "string"},
            "aggregate_id": {"type": "string"},
            "occurred_at": {"type": "string", "pattern": "Z$"},
            "producer": {"const": "research-agent-service"},
            "trace_id": {"type": "string"},
            "correlation_id": {"type": "string"},
            "data": data_schema,
        },
    }


_CITATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source_type", "ref", "score"],
    "properties": {
        "source_type": {"enum": ["product", "price_analysis", "web"]},
        "ref": {"type": "string"},
        "score": {"type": ["string", "null"]},
    },
}
_DEGRADATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dependency", "reason"],
    "properties": {
        "dependency": {"type": "string"},
        "reason": {"type": "string"},
    },
}
_COMPLETED_DATA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "conversation_id",
        "query_hash",
        "tools_used",
        "citations",
        "confidence",
        "degradations",
        "usage",
        "loop_steps",
        "model",
        "prompt_version",
    ],
    "properties": {
        "conversation_id": {"type": "string"},
        "query_hash": {"type": "string"},
        "tools_used": {"type": "array", "items": {"type": "string"}},
        "citations": {"type": "array", "items": _CITATION},
        "confidence": {"type": ["string", "null"]},
        "degradations": {"type": "array", "items": _DEGRADATION},
        "usage": {
            "type": "object",
            "additionalProperties": False,
            "required": ["prompt_tokens", "completion_tokens"],
            "properties": {
                "prompt_tokens": {"type": "integer"},
                "completion_tokens": {"type": "integer"},
            },
        },
        "loop_steps": {"type": "integer"},
        "model": {"type": "string"},
        "prompt_version": {"type": "string"},
    },
}
_FAILED_DATA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "conversation_id",
        "query_hash",
        "error_code",
        "error_category",
        "stage",
        "tools_attempted",
        "degradations",
    ],
    "properties": {
        "conversation_id": {"type": "string"},
        "query_hash": {"type": "string"},
        "error_code": {"type": ["string", "null"]},
        "error_category": {"type": ["string", "null"]},
        "stage": {"type": ["string", "null"]},
        "tools_attempted": {"type": "array", "items": {"type": "string"}},
        "degradations": {"type": "array", "items": _DEGRADATION},
    },
}
_FEEDBACK_DATA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "agent_run_id",
        "conversation_id",
        "rating",
        "reason",
        "labels",
    ],
    "properties": {
        "agent_run_id": {"type": "string"},
        "conversation_id": {"type": "string"},
        "rating": {"enum": ["up", "down"]},
        "reason": {"type": ["string", "null"]},
        "labels": {"type": "array", "items": {"type": "string"}},
    },
}
_EVALUATION_DATA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["agent_run_id", "reason"],
    "properties": {
        "agent_run_id": {"type": "string"},
        "reason": {"type": "string"},
    },
}


def _run(*, trace: bool = False) -> AgentRun:
    return AgentRun(
        id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        query_message_id=MessageId(UUID(int=3)),
        model="qwen3",
        prompt_version="v1",
        started_at=_NOW,
        trace_id="trace-1" if trace else None,
        correlation_id="corr-1" if trace else None,
    )


def _tool_call() -> ToolCall:
    return ToolCall(
        id=ToolCallId(UUID(int=10)),
        agent_run_id=AgentRunId(UUID(int=1)),
        step_index=0,
        tool=ToolName.PRODUCT_CATALOG_RAG,
        status=ToolCallStatus.OK,
        started_at=_NOW,
        finished_at=_NOW,
        latency_ms=10,
    )


def _citation() -> Citation:
    return Citation(
        source_type=CitationType.PRODUCT,
        ref="SKU-1",
        title="Наушники",
        snippet="s",
        position=0,
        retrieved_at=_NOW,
        score=Decimal("0.9"),
    )


def test_query_completed_matches_schema() -> None:
    """agent.query.completed.v1 соответствует контракту (с trace_id)."""
    run = _run(trace=True)
    run.record_tool_call(_tool_call())
    run.complete(
        answer_message_id=MessageId(UUID(int=4)),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        confidence=Confidence.HIGH,
        degradations=(Degradation("reranker", "unavailable"),),
        loop_steps=3,
        now=_NOW,
    )

    message = build_query_completed_message(
        run,
        (_citation(),),
        event_id=UUID(int=99),
        query_hash="h",
        occurred_at=_NOW,
    )

    validate(
        instance=message.payload,
        schema=_envelope(EVENT_QUERY_COMPLETED, _COMPLETED_DATA),
    )
    assert message.headers["event_type"] == EVENT_QUERY_COMPLETED


def test_query_failed_matches_schema() -> None:
    """agent.query.failed.v1 соответствует контракту."""
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

    message = build_query_failed_message(
        run, event_id=UUID(int=99), query_hash="h", occurred_at=_NOW
    )

    validate(
        instance=message.payload,
        schema=_envelope(EVENT_QUERY_FAILED, _FAILED_DATA),
    )


def test_feedback_received_matches_schema() -> None:
    """agent.feedback.received.v1 соответствует контракту."""
    feedback = Feedback(
        id=FeedbackId(UUID(int=20)),
        agent_run_id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        rating=FeedbackRating.DOWN,
        created_at=_NOW,
        reason="неточно",
        labels=("hallucination",),
    )

    message = build_feedback_received_message(
        feedback, event_id=UUID(int=99), occurred_at=_NOW
    )

    validate(
        instance=message.payload,
        schema=_envelope(EVENT_FEEDBACK_RECEIVED, _FEEDBACK_DATA),
    )


def test_evaluation_requested_matches_schema() -> None:
    """agent.evaluation.requested.v1 соответствует контракту."""
    message = build_evaluation_requested_message(
        evaluation_id=UUID(int=30),
        agent_run_id=AgentRunId(UUID(int=1)),
        reason="negative_feedback",
        event_id=UUID(int=99),
        occurred_at=_NOW,
    )

    validate(
        instance=message.payload,
        schema=_envelope(EVENT_EVALUATION_REQUESTED, _EVALUATION_DATA),
    )
