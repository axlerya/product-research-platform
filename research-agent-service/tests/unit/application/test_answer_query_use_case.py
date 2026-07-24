"""Тесты AnswerQueryUseCase — синхронного оркестратора запроса."""

from decimal import Decimal
from uuid import UUID

import pytest

from research_agent_service.application.dto.answer import (
    AgentOutcome,
    AnswerQueryCommand,
)
from research_agent_service.application.event_mapping import (
    EVENT_QUERY_COMPLETED,
    EVENT_QUERY_FAILED,
)
from research_agent_service.application.exceptions import (
    QueryFailed,
    RateLimited,
)
from research_agent_service.application.services.source_validation import (
    SourceValidator,
)
from research_agent_service.application.use_cases.answer_query import (
    AnswerQueryUseCase,
)
from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    Confidence,
    MessageRole,
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
from research_agent_service.domain.value_objects.query import Query
from research_agent_service.domain.value_objects.usage import TokenUsage
from tests.support.fakes import (
    FIXED_NOW,
    FakeClock,
    FakeIdGenerator,
    FakeOrchestrator,
    FakeRateLimiter,
    FakeUnitOfWork,
)


def _citation(ref: str, position: int = 0) -> Citation:
    return Citation(
        source_type=CitationType.PRODUCT,
        ref=ref,
        title="Наушники",
        snippet="описание",
        position=position,
        retrieved_at=FIXED_NOW,
        score=Decimal("0.9"),
    )


def _tool_call() -> ToolCall:
    return ToolCall(
        id=ToolCallId(UUID(int=50)),
        agent_run_id=AgentRunId(UUID(int=51)),
        step_index=0,
        tool=ToolName.PRODUCT_CATALOG_RAG,
        status=ToolCallStatus.OK,
        started_at=FIXED_NOW,
        finished_at=FIXED_NOW,
        latency_ms=100,
    )


def _outcome(
    *,
    citations: tuple[Citation, ...] = (),
    retrieved_refs: tuple[str, ...] = (),
) -> AgentOutcome:
    return AgentOutcome(
        answer="вот ответ",
        citations=citations,
        tool_calls=(_tool_call(),),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        confidence=Confidence.HIGH,
        used_tools=(ToolName.PRODUCT_CATALOG_RAG,),
        retrieved_refs=retrieved_refs,
        loop_steps=2,
    )


def _use_case(
    uow: FakeUnitOfWork,
    *,
    orchestrator: FakeOrchestrator | None = None,
    rate_limiter: FakeRateLimiter | None = None,
) -> AnswerQueryUseCase:
    return AnswerQueryUseCase(
        uow=uow,
        orchestrator=orchestrator or FakeOrchestrator(outcome=_outcome()),
        rate_limiter=rate_limiter or FakeRateLimiter(),
        source_validator=SourceValidator(),
        id_generator=FakeIdGenerator(),
        clock=FakeClock(),
    )


def _command() -> AnswerQueryCommand:
    return AnswerQueryCommand(
        query=Query(text="найди наушники"), client_principal="client-1"
    )


async def test_completed_query_persists_run_and_event() -> None:
    """Успех: прогон, вызовы и событие completed — в одной транзакции."""
    outcome = _outcome(
        citations=(_citation("SKU-1"),), retrieved_refs=("SKU-1",)
    )
    uow = FakeUnitOfWork()

    result = await _use_case(
        uow, orchestrator=FakeOrchestrator(outcome=outcome)
    ).execute(_command())

    assert result.status is RunStatus.COMPLETED
    assert result.answer == "вот ответ"
    assert len(result.citations) == 1
    assert uow.committed
    assert len(uow.agent_runs.added) == 1
    assert uow.agent_runs.added[0].tool_call_count == 1
    assert [m.event_type for m in uow.outbox.messages] == [
        EVENT_QUERY_COMPLETED
    ]
    assert len(uow.conversations.added_messages) == 2


async def test_dangling_citation_dropped_and_degraded() -> None:
    """Цитата на неизвестный факт отбрасывается → прогон degraded."""
    outcome = _outcome(
        citations=(_citation("SKU-1"), _citation("SKU-GHOST", position=1)),
        retrieved_refs=("SKU-1",),
    )
    uow = FakeUnitOfWork()

    result = await _use_case(
        uow, orchestrator=FakeOrchestrator(outcome=outcome)
    ).execute(_command())

    assert result.status is RunStatus.DEGRADED
    assert len(result.citations) == 1
    assert any(d.dependency == "citations" for d in result.degradations)


async def test_rate_limited_raises_and_skips_persist() -> None:
    """Превышение лимита → RateLimited, ничего не пишется."""
    uow = FakeUnitOfWork()

    with pytest.raises(RateLimited):
        await _use_case(
            uow, rate_limiter=FakeRateLimiter(allowed=False, retry_after_s=5.0)
        ).execute(_command())

    assert not uow.committed
    assert uow.agent_runs.added == []


async def test_orchestrator_failure_persists_failed_event() -> None:
    """Сбой оркестратора → прогон failed + событие failed, QueryFailed."""
    uow = FakeUnitOfWork()

    with pytest.raises(QueryFailed):
        await _use_case(
            uow, orchestrator=FakeOrchestrator(error=RuntimeError("boom"))
        ).execute(_command())

    assert uow.committed
    assert uow.agent_runs.added[0].status is RunStatus.FAILED
    assert [m.event_type for m in uow.outbox.messages] == [EVENT_QUERY_FAILED]


async def test_existing_conversation_loads_history() -> None:
    """Существующий диалог: история грузится, диалог не пере-создаётся."""
    conv_id = ConversationId(UUID(int=999))
    uow = FakeUnitOfWork()
    existing = Conversation(id=conv_id, created_at=FIXED_NOW, message_count=2)
    uow.conversations._store[conv_id.value] = existing
    prior = Message(
        id=MessageId(UUID(int=888)),
        conversation_id=conv_id,
        role=MessageRole.USER,
        content="ранее",
        created_at=FIXED_NOW,
    )
    uow.conversations.history = (prior,)
    orchestrator = FakeOrchestrator(
        outcome=_outcome(
            citations=(_citation("SKU-1"),), retrieved_refs=("SKU-1",)
        )
    )
    command = AnswerQueryCommand(
        query=Query(text="ещё"),
        client_principal="c1",
        conversation_id=conv_id,
    )

    await _use_case(uow, orchestrator=orchestrator).execute(command)

    assert orchestrator.history == (prior,)
    assert uow.conversations.added == []


async def test_missing_conversation_creates_fresh() -> None:
    """conversation_id задан, но не найден → создаётся новый диалог с ним."""
    conv_id = ConversationId(UUID(int=777))
    uow = FakeUnitOfWork()
    command = AnswerQueryCommand(
        query=Query(text="привет"),
        client_principal="c1",
        conversation_id=conv_id,
    )
    orchestrator = FakeOrchestrator(
        outcome=_outcome(
            citations=(_citation("SKU-1"),), retrieved_refs=("SKU-1",)
        )
    )

    result = await _use_case(uow, orchestrator=orchestrator).execute(command)

    assert result.conversation_id == conv_id
    assert len(uow.conversations.added) == 1
