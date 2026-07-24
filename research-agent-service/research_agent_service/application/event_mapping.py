"""Построение конвертов событий и записей outbox из доменных данных.

Конверт строит application-слой (не домен): event_id == outbox.id (uuidv7,
передаётся вызывающим), aggregate_id — id соответствующего агрегата,
occurred_at — RFC3339 UTC с суффиксом Z. trace_id/correlation_id
прокидываются и в конверт, и в headers для relay.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from uuid import UUID

from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.identifiers import AgentRunId

_PRODUCER = "research-agent-service"
_EVENT_VERSION = "1.0"

EVENT_QUERY_COMPLETED = "agent.query.completed.v1"
EVENT_QUERY_FAILED = "agent.query.failed.v1"
EVENT_FEEDBACK_RECEIVED = "agent.feedback.received.v1"
EVENT_EVALUATION_REQUESTED = "agent.evaluation.requested.v1"

_AGGREGATE_RUN = "agent_run"
_AGGREGATE_FEEDBACK = "agent_feedback"
_AGGREGATE_EVALUATION = "agent_evaluation"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _headers(
    event_type: str, trace_id: str | None, correlation_id: str | None
) -> dict[str, str]:
    headers = {"event_type": event_type}
    if trace_id is not None:
        headers["trace_id"] = trace_id
    if correlation_id is not None:
        headers["correlation_id"] = correlation_id
    return headers


def _tools_used(run: AgentRun) -> list[str]:
    return sorted({call.tool.value for call in run.tool_calls})


def _citation_data(citations: Iterable[Citation]) -> list[dict[str, object]]:
    return [
        {
            "source_type": citation.source_type.value,
            "ref": citation.ref,
            "score": str(citation.score)
            if citation.score is not None
            else None,
        }
        for citation in citations
    ]


def _degradation_data(
    degradations: Iterable[Degradation],
) -> list[dict[str, str]]:
    return [
        {"dependency": item.dependency, "reason": item.reason}
        for item in degradations
    ]


def _message(
    *,
    event_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    occurred_at: datetime,
    data: Mapping[str, object],
    trace_id: str | None,
    correlation_id: str | None,
) -> OutboxMessage:
    envelope: dict[str, object] = {
        "event_id": str(event_id),
        "event_type": event_type,
        "event_version": _EVENT_VERSION,
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "occurred_at": _iso(occurred_at),
        "producer": _PRODUCER,
        "data": data,
    }
    if trace_id is not None:
        envelope["trace_id"] = trace_id
    if correlation_id is not None:
        envelope["correlation_id"] = correlation_id
    return OutboxMessage(
        id=event_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=envelope,
        occurred_at=occurred_at,
        headers=_headers(event_type, trace_id, correlation_id),
    )


def build_query_completed_message(
    run: AgentRun,
    citations: Iterable[Citation],
    *,
    event_id: UUID,
    query_hash: str,
    occurred_at: datetime,
) -> OutboxMessage:
    """Событие agent.query.completed.v1 из завершённого прогона."""
    data: dict[str, object] = {
        "conversation_id": str(run.conversation_id.value),
        "query_hash": query_hash,
        "tools_used": _tools_used(run),
        "citations": _citation_data(citations),
        "confidence": run.confidence.value
        if run.confidence is not None
        else None,
        "degradations": _degradation_data(run.degradations),
        "usage": {
            "prompt_tokens": run.usage.prompt_tokens,
            "completion_tokens": run.usage.completion_tokens,
        },
        "loop_steps": run.loop_steps,
        "model": run.model,
        "prompt_version": run.prompt_version,
    }
    return _message(
        event_id=event_id,
        event_type=EVENT_QUERY_COMPLETED,
        aggregate_type=_AGGREGATE_RUN,
        aggregate_id=run.id.value,
        occurred_at=occurred_at,
        data=data,
        trace_id=run.trace_id,
        correlation_id=run.correlation_id,
    )


def build_query_failed_message(
    run: AgentRun,
    *,
    event_id: UUID,
    query_hash: str,
    occurred_at: datetime,
) -> OutboxMessage:
    """Событие agent.query.failed.v1 из проваленного прогона."""
    error = run.error
    data: dict[str, object] = {
        "conversation_id": str(run.conversation_id.value),
        "query_hash": query_hash,
        "error_code": error.code.value if error is not None else None,
        "error_category": error.category.value if error is not None else None,
        "stage": error.stage.value if error is not None else None,
        "tools_attempted": _tools_used(run),
        "degradations": _degradation_data(run.degradations),
    }
    return _message(
        event_id=event_id,
        event_type=EVENT_QUERY_FAILED,
        aggregate_type=_AGGREGATE_RUN,
        aggregate_id=run.id.value,
        occurred_at=occurred_at,
        data=data,
        trace_id=run.trace_id,
        correlation_id=run.correlation_id,
    )


def build_feedback_received_message(
    feedback: Feedback, *, event_id: UUID, occurred_at: datetime
) -> OutboxMessage:
    """Событие agent.feedback.received.v1 из обратной связи."""
    data: dict[str, object] = {
        "agent_run_id": str(feedback.agent_run_id.value),
        "conversation_id": str(feedback.conversation_id.value),
        "rating": feedback.rating.value,
        "reason": feedback.reason,
        "labels": list(feedback.labels),
    }
    return _message(
        event_id=event_id,
        event_type=EVENT_FEEDBACK_RECEIVED,
        aggregate_type=_AGGREGATE_FEEDBACK,
        aggregate_id=feedback.id.value,
        occurred_at=occurred_at,
        data=data,
        trace_id=None,
        correlation_id=None,
    )


def build_evaluation_requested_message(
    *,
    evaluation_id: UUID,
    agent_run_id: AgentRunId,
    reason: str,
    event_id: UUID,
    occurred_at: datetime,
) -> OutboxMessage:
    """Событие agent.evaluation.requested.v1 (агрегат — логический)."""
    data: dict[str, object] = {
        "agent_run_id": str(agent_run_id.value),
        "reason": reason,
    }
    return _message(
        event_id=event_id,
        event_type=EVENT_EVALUATION_REQUESTED,
        aggregate_type=_AGGREGATE_EVALUATION,
        aggregate_id=evaluation_id,
        occurred_at=occurred_at,
        data=data,
        trace_id=None,
        correlation_id=None,
    )
