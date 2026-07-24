"""Интеграционные тесты персистентности (PostgreSQL в контейнере)."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    FeedbackRating,
    MessageRole,
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
from research_agent_service.domain.value_objects.usage import TokenUsage
from research_agent_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _conversation(n: int) -> Conversation:
    return Conversation(id=ConversationId(UUID(int=n)), created_at=_NOW)


def _completed_run(conv: Conversation, n: int) -> AgentRun:
    run = AgentRun(
        id=AgentRunId(UUID(int=n)),
        conversation_id=conv.id,
        query_message_id=MessageId(UUID(int=n + 100)),
        model="claude-opus-4-8",
        prompt_version="v1",
        started_at=_NOW,
    )
    run.record_tool_call(
        ToolCall(
            id=ToolCallId(UUID(int=n + 200)),
            agent_run_id=run.id,
            step_index=0,
            tool=ToolName.PRODUCT_CATALOG_RAG,
            status=ToolCallStatus.OK,
            started_at=_NOW,
            finished_at=_NOW,
            latency_ms=100,
        )
    )
    run.complete(
        answer_message_id=MessageId(UUID(int=n + 300)),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        confidence=Confidence.HIGH,
        degradations=(),
        loop_steps=1,
        now=_NOW,
    )
    return run


async def test_uow_persists_run_and_outbox_atomically(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Прогон, вызов инструмента и событие сохраняются одной транзакцией."""
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    conv = _conversation(1)
    run = _completed_run(conv, 2)
    outbox = OutboxMessage(
        id=UUID(int=9),
        aggregate_type="agent_run",
        aggregate_id=run.id.value,
        event_type="agent.query.completed.v1",
        payload={"k": "v"},
        occurred_at=_NOW,
    )

    async with uow:
        await uow.conversations.add(conv)
        await uow.agent_runs.add(run)
        await uow.outbox.add_many([outbox])
        await uow.commit()

    async with uow:
        loaded = await uow.agent_runs.get(run.id)

    assert loaded is not None
    assert loaded.status is RunStatus.COMPLETED
    assert loaded.usage.total == 15
    assert loaded.tool_call_count == 1


async def test_rollback_on_error_persists_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Исключение внутри транзакции → ничего не сохранено."""
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    conv = _conversation(5)

    with pytest.raises(RuntimeError):
        async with uow:
            await uow.conversations.add(conv)
            raise RuntimeError("boom")

    async with uow:
        loaded = await uow.conversations.get(conv.id)

    assert loaded is None


async def test_list_and_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Список прогонов (с фильтрами и без) и история сообщений."""
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    conv = _conversation(7)
    run = _completed_run(conv, 8)
    message = Message(
        id=MessageId(UUID(int=10)),
        conversation_id=conv.id,
        role=MessageRole.USER,
        content="вопрос",
        created_at=_NOW,
    )

    async with uow:
        await uow.conversations.add(conv)
        await uow.conversations.add_message(message)
        await uow.agent_runs.add(run)
        await uow.commit()

    async with uow:
        filtered = await uow.agent_runs.list(
            conversation_id=conv.id,
            status=RunStatus.COMPLETED,
            limit=10,
            offset=0,
        )
        unfiltered = await uow.agent_runs.list(limit=10, offset=0)
        history = await uow.conversations.load_history(conv.id, limit=10)

    assert len(filtered) == 1
    assert filtered[0].tool_call_count == 1
    assert len(unfiltered) == 1
    assert len(history) == 1
    assert history[0].content == "вопрос"


async def test_feedback_missing_run_and_explicit_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Обратная связь сохраняется; get отсутствующего → None; rollback()."""
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    conv = _conversation(20)
    run = _completed_run(conv, 21)
    feedback = Feedback(
        id=FeedbackId(UUID(int=22)),
        agent_run_id=run.id,
        conversation_id=conv.id,
        rating=FeedbackRating.UP,
        created_at=_NOW,
    )

    async with uow:
        await uow.conversations.add(conv)
        await uow.agent_runs.add(run)
        await uow.feedback.add(feedback)
        await uow.commit()

    async with uow:
        missing = await uow.agent_runs.get(AgentRunId(UUID(int=999)))
    assert missing is None

    async with uow:
        await uow.conversations.add(_conversation(23))
        await uow.rollback()
    async with uow:
        assert await uow.conversations.get(ConversationId(UUID(int=23))) is None


async def test_get_message_returns_stored_or_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """get_message возвращает сохранённое сообщение или None."""
    conv = _conversation(70)
    message = Message(
        id=MessageId(UUID(int=71)),
        conversation_id=conv.id,
        role=MessageRole.USER,
        content="привет",
        created_at=_NOW,
    )
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    async with uow:
        await uow.conversations.add(conv)
        await uow.conversations.add_message(message)
        await uow.commit()

    async with uow:
        loaded = await uow.conversations.get_message(MessageId(UUID(int=71)))
        missing = await uow.conversations.get_message(MessageId(UUID(int=72)))

    assert loaded is not None
    assert loaded.content == "привет"
    assert missing is None
