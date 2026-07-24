"""Тесты мапперов домен ↔ ORM (round-trip)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

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
from research_agent_service.infrastructure.db.mappers import (
    agent_run_from_orm,
    agent_run_to_orm,
    conversation_from_orm,
    conversation_to_orm,
    feedback_from_orm,
    feedback_to_orm,
    message_from_orm,
    message_to_orm,
    outbox_to_orm,
    tool_call_to_orm,
)

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
_CONV = ConversationId(UUID(int=1))
_RUN = AgentRunId(UUID(int=3))


def _base_run() -> AgentRun:
    return AgentRun(
        id=_RUN,
        conversation_id=_CONV,
        query_message_id=MessageId(UUID(int=2)),
        model="claude-opus-4-8",
        prompt_version="v1",
        started_at=_NOW,
        trace_id="tr",
    )


def test_conversation_round_trip() -> None:
    """Диалог сохраняет счётчик и заголовок."""
    conv = Conversation(
        id=_CONV,
        created_at=_NOW,
        title="Поиск",
        message_count=3,
        updated_at=_NOW,
    )

    back = conversation_from_orm(conversation_to_orm(conv))

    assert back.id == _CONV
    assert back.title == "Поиск"
    assert back.message_count == 3


def test_assistant_message_round_trip_with_citation() -> None:
    """Ответ ассистента: цитата (со скором) и ссылка на прогон сохраняются."""
    citation = Citation(
        source_type=CitationType.PRODUCT,
        ref="SKU-1",
        title="Наушники",
        snippet="описание",
        position=0,
        retrieved_at=_NOW,
        score=Decimal("0.9"),
    )
    message = Message(
        id=MessageId(UUID(int=2)),
        conversation_id=_CONV,
        role=MessageRole.ASSISTANT,
        content="ответ",
        created_at=_NOW,
        agent_run_id=_RUN,
        citations=(citation,),
        token_count=42,
    )

    back = message_from_orm(message_to_orm(message))

    assert back.role is MessageRole.ASSISTANT
    assert back.citations[0].ref == "SKU-1"
    assert back.citations[0].score == Decimal("0.9")
    assert back.agent_run_id == _RUN
    assert back.token_count == 42


def test_user_message_round_trip_without_run() -> None:
    """Сообщение пользователя: без прогона, цитат и токенов."""
    message = Message(
        id=MessageId(UUID(int=4)),
        conversation_id=_CONV,
        role=MessageRole.USER,
        content="вопрос",
        created_at=_NOW,
    )

    back = message_from_orm(message_to_orm(message))

    assert back.agent_run_id is None
    assert back.citations == ()
    assert back.token_count is None


def test_completed_agent_run_round_trip() -> None:
    """Завершённый прогон с вызовом инструмента и деградацией."""
    run = _base_run()
    provenance = (
        Citation(
            source_type=CitationType.WEB,
            ref="https://a",
            title="t",
            snippet="s",
            position=0,
            retrieved_at=_NOW,
        ),
    )
    call = ToolCall(
        id=ToolCallId(UUID(int=5)),
        agent_run_id=_RUN,
        step_index=0,
        tool=ToolName.PRODUCT_CATALOG_RAG,
        status=ToolCallStatus.OK,
        started_at=_NOW,
        finished_at=_NOW,
        latency_ms=100,
        provenance=provenance,
    )
    run.record_tool_call(call)
    run.complete(
        answer_message_id=MessageId(UUID(int=9)),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        confidence=Confidence.HIGH,
        degradations=(Degradation("reranker", "unavailable"),),
        loop_steps=2,
        now=_NOW,
    )

    orm = agent_run_to_orm(run)
    call_orms = [tool_call_to_orm(c) for c in run.tool_calls]
    back = agent_run_from_orm(orm, call_orms)

    assert back.status is RunStatus.DEGRADED
    assert back.usage.total == 150
    assert back.confidence is Confidence.HIGH
    assert back.tool_call_count == 1
    assert back.tool_calls[0].provenance[0].score is None
    assert back.answer_message_id == MessageId(UUID(int=9))
    assert back.degradations[0].dependency == "reranker"
    assert back.trace_id == "tr"
    assert back.error is None


def test_failed_agent_run_round_trip() -> None:
    """Проваленный прогон: ошибка восстанавливается, поля успеха пусты."""
    run = _base_run()
    run.fail(
        error=RunError(
            code=ErrorCode.LLM_UNAVAILABLE,
            category=ErrorCategory.UPSTREAM,
            stage=RunStage.PLAN,
            message="провайдер недоступен",
        ),
        now=_NOW,
    )

    back = agent_run_from_orm(agent_run_to_orm(run), [])

    assert back.status is RunStatus.FAILED
    assert back.error is not None
    assert back.error.code is ErrorCode.LLM_UNAVAILABLE
    assert back.confidence is None
    assert back.answer_message_id is None


def test_feedback_round_trip() -> None:
    """Обратная связь сохраняет рейтинг и метки."""
    feedback = Feedback(
        id=FeedbackId(UUID(int=6)),
        agent_run_id=_RUN,
        conversation_id=_CONV,
        rating=FeedbackRating.DOWN,
        created_at=_NOW,
        reason="неточно",
        labels=("pricing",),
    )

    back = feedback_from_orm(feedback_to_orm(feedback))

    assert back.rating is FeedbackRating.DOWN
    assert back.labels == ("pricing",)


def test_outbox_to_orm() -> None:
    """OutboxMessage → ORM переносит конверт и headers."""
    message = OutboxMessage(
        id=UUID(int=7),
        aggregate_type="agent_run",
        aggregate_id=UUID(int=3),
        event_type="agent.query.completed.v1",
        payload={"k": "v"},
        occurred_at=_NOW,
        headers={"trace_id": "t"},
    )

    orm = outbox_to_orm(message, created_at=_NOW)

    assert orm.id == UUID(int=7)
    assert orm.event_type == "agent.query.completed.v1"
    assert orm.headers == {"trace_id": "t"}
