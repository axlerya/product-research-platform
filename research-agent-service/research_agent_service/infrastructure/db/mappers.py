"""Мапперы домен ↔ ORM (Data Mapper; домен не знает SQLAlchemy)."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    Confidence,
    ErrorCategory,
    ErrorCode,
    FeedbackRating,
    MessageRole,
    RunStage,
    RunStatus,
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
from research_agent_service.infrastructure.db.models import (
    AgentRunORM,
    ConversationORM,
    FeedbackORM,
    MessageORM,
    OutboxEventORM,
    ToolCallORM,
)


def _citation_to_json(citation: Citation) -> dict[str, object]:
    return {
        "source_type": citation.source_type.value,
        "ref": citation.ref,
        "title": citation.title,
        "snippet": citation.snippet,
        "position": citation.position,
        "retrieved_at": citation.retrieved_at.isoformat(),
        "score": str(citation.score) if citation.score is not None else None,
    }


def _citation_from_json(data: Mapping[str, object]) -> Citation:
    score = data["score"]
    return Citation(
        source_type=CitationType(data["source_type"]),
        ref=str(data["ref"]),
        title=str(data["title"]),
        snippet=str(data["snippet"]),
        position=int(data["position"]),  # type: ignore[call-overload]
        retrieved_at=datetime.fromisoformat(str(data["retrieved_at"])),
        score=Decimal(str(score)) if score is not None else None,
    )


def conversation_to_orm(conversation: Conversation) -> ConversationORM:
    """Диалог → ORM."""
    return ConversationORM(
        id=conversation.id.value,
        title=conversation.title,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def conversation_from_orm(orm: ConversationORM) -> Conversation:
    """ORM → диалог."""
    return Conversation(
        id=ConversationId(orm.id),
        title=orm.title,
        message_count=orm.message_count,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def message_to_orm(message: Message) -> MessageORM:
    """Сообщение → ORM."""
    return MessageORM(
        id=message.id.value,
        conversation_id=message.conversation_id.value,
        role=message.role.value,
        content=message.content,
        citations=[_citation_to_json(c) for c in message.citations],
        token_count=message.token_count,
        agent_run_id=(
            message.agent_run_id.value
            if message.agent_run_id is not None
            else None
        ),
        created_at=message.created_at,
    )


def message_from_orm(orm: MessageORM) -> Message:
    """ORM → сообщение."""
    return Message(
        id=MessageId(orm.id),
        conversation_id=ConversationId(orm.conversation_id),
        role=MessageRole(orm.role),
        content=orm.content,
        created_at=orm.created_at,
        agent_run_id=(
            AgentRunId(orm.agent_run_id)
            if orm.agent_run_id is not None
            else None
        ),
        citations=tuple(_citation_from_json(c) for c in orm.citations),
        token_count=orm.token_count,
    )


def tool_call_to_orm(call: ToolCall) -> ToolCallORM:
    """Вызов инструмента → ORM."""
    return ToolCallORM(
        id=call.id.value,
        agent_run_id=call.agent_run_id.value,
        step_index=call.step_index,
        tool=call.tool.value,
        status=call.status.value,
        arguments=dict(call.arguments),
        result_summary=dict(call.result_summary),
        provenance=[_citation_to_json(c) for c in call.provenance],
        latency_ms=call.latency_ms,
        error=call.error,
        started_at=call.started_at,
        finished_at=call.finished_at,
    )


def tool_call_from_orm(orm: ToolCallORM) -> ToolCall:
    """ORM → вызов инструмента."""
    return ToolCall(
        id=ToolCallId(orm.id),
        agent_run_id=AgentRunId(orm.agent_run_id),
        step_index=orm.step_index,
        tool=ToolName(orm.tool),
        status=ToolCallStatus(orm.status),
        started_at=orm.started_at,
        finished_at=orm.finished_at,
        latency_ms=orm.latency_ms,
        arguments=dict(orm.arguments),
        result_summary=dict(orm.result_summary),
        provenance=tuple(_citation_from_json(c) for c in orm.provenance),
        error=orm.error,
    )


def agent_run_to_orm(run: AgentRun) -> AgentRunORM:
    """Прогон → ORM (без вложенных вызовов — они мапятся отдельно)."""
    error = run.error
    return AgentRunORM(
        id=run.id.value,
        conversation_id=run.conversation_id.value,
        query_message_id=run.query_message_id.value,
        answer_message_id=(
            run.answer_message_id.value
            if run.answer_message_id is not None
            else None
        ),
        status=run.status.value,
        client_principal=run.client_principal,
        model=run.model,
        prompt_version=run.prompt_version,
        prompt_tokens=run.usage.prompt_tokens,
        completion_tokens=run.usage.completion_tokens,
        loop_steps=run.loop_steps,
        tool_call_count=run.tool_call_count,
        confidence=run.confidence.value if run.confidence is not None else None,
        degradations=[
            {"dependency": d.dependency, "reason": d.reason}
            for d in run.degradations
        ],
        error=(
            {
                "code": error.code.value,
                "category": error.category.value,
                "stage": error.stage.value,
                "message": error.message,
            }
            if error is not None
            else None
        ),
        idempotency_key=run.idempotency_key,
        trace_id=run.trace_id,
        correlation_id=run.correlation_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def agent_run_from_orm(
    orm: AgentRunORM, tool_calls: Sequence[ToolCallORM]
) -> AgentRun:
    """ORM (+ вызовы) → прогон."""
    error = None
    if orm.error is not None:
        error = RunError(
            code=ErrorCode(orm.error["code"]),
            category=ErrorCategory(orm.error["category"]),
            stage=RunStage(orm.error["stage"]),
            message=str(orm.error["message"]),
        )
    return AgentRun.reconstitute(
        id=AgentRunId(orm.id),
        conversation_id=ConversationId(orm.conversation_id),
        query_message_id=MessageId(orm.query_message_id),
        model=orm.model,
        prompt_version=orm.prompt_version,
        status=RunStatus(orm.status),
        started_at=orm.started_at,
        finished_at=orm.finished_at,
        usage=TokenUsage(
            prompt_tokens=orm.prompt_tokens,
            completion_tokens=orm.completion_tokens,
        ),
        loop_steps=orm.loop_steps,
        confidence=(
            Confidence(orm.confidence) if orm.confidence is not None else None
        ),
        answer_message_id=(
            MessageId(orm.answer_message_id)
            if orm.answer_message_id is not None
            else None
        ),
        degradations=tuple(
            Degradation(d["dependency"], d["reason"]) for d in orm.degradations
        ),
        error=error,
        tool_calls=tuple(tool_call_from_orm(tc) for tc in tool_calls),
        client_principal=orm.client_principal,
        idempotency_key=orm.idempotency_key,
        trace_id=orm.trace_id,
        correlation_id=orm.correlation_id,
    )


def feedback_to_orm(feedback: Feedback) -> FeedbackORM:
    """Обратная связь → ORM."""
    return FeedbackORM(
        id=feedback.id.value,
        agent_run_id=feedback.agent_run_id.value,
        conversation_id=feedback.conversation_id.value,
        rating=feedback.rating.value,
        reason=feedback.reason,
        labels=list(feedback.labels),
        created_at=feedback.created_at,
    )


def feedback_from_orm(orm: FeedbackORM) -> Feedback:
    """ORM → обратная связь."""
    return Feedback(
        id=FeedbackId(orm.id),
        agent_run_id=AgentRunId(orm.agent_run_id),
        conversation_id=ConversationId(orm.conversation_id),
        rating=FeedbackRating(orm.rating),
        created_at=orm.created_at,
        reason=orm.reason,
        labels=tuple(orm.labels),
    )


def outbox_to_orm(
    message: OutboxMessage, *, created_at: datetime
) -> OutboxEventORM:
    """Событие outbox → ORM."""
    return OutboxEventORM(
        id=message.id,
        aggregate_type=message.aggregate_type,
        aggregate_id=message.aggregate_id,
        event_type=message.event_type,
        payload=dict(message.payload),
        headers=dict(message.headers),
        occurred_at=message.occurred_at,
        created_at=created_at,
        next_attempt_at=message.next_attempt_at,
    )
