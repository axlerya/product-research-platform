"""Тесты SubmitFeedbackUseCase."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from research_agent_service.application.dto.feedback import (
    SubmitFeedbackCommand,
)
from research_agent_service.application.event_mapping import (
    EVENT_EVALUATION_REQUESTED,
    EVENT_FEEDBACK_RECEIVED,
)
from research_agent_service.application.exceptions import UnknownAgentRun
from research_agent_service.application.use_cases.submit_feedback import (
    SubmitFeedbackUseCase,
)
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)
from tests.support.fakes import FakeClock, FakeIdGenerator, FakeUnitOfWork

_RUN_ID = AgentRunId(UUID(int=1))


def _run() -> AgentRun:
    return AgentRun(
        id=_RUN_ID,
        conversation_id=ConversationId(UUID(int=2)),
        query_message_id=MessageId(UUID(int=3)),
        model="claude-opus-4-8",
        prompt_version="v1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _use_case(uow: FakeUnitOfWork) -> SubmitFeedbackUseCase:
    return SubmitFeedbackUseCase(
        uow=uow, id_generator=FakeIdGenerator(), clock=FakeClock()
    )


async def test_positive_feedback_emits_single_event() -> None:
    """Позитивная оценка: только feedback_received, транзакция коммитится."""
    uow = FakeUnitOfWork(run=_run())

    await _use_case(uow).execute(
        SubmitFeedbackCommand(agent_run_id=_RUN_ID, rating=FeedbackRating.UP)
    )

    assert len(uow.feedback.added) == 1
    assert [m.event_type for m in uow.outbox.messages] == [
        EVENT_FEEDBACK_RECEIVED
    ]
    assert uow.committed


async def test_negative_feedback_also_requests_evaluation() -> None:
    """Негативная оценка: дополнительно evaluation_requested."""
    uow = FakeUnitOfWork(run=_run())

    await _use_case(uow).execute(
        SubmitFeedbackCommand(
            agent_run_id=_RUN_ID,
            rating=FeedbackRating.DOWN,
            reason="неточные цены",
        )
    )

    types = [m.event_type for m in uow.outbox.messages]
    assert EVENT_FEEDBACK_RECEIVED in types
    assert EVENT_EVALUATION_REQUESTED in types


async def test_unknown_run_raises_and_does_not_commit() -> None:
    """Обратная связь к несуществующему прогону → ошибка, без коммита."""
    uow = FakeUnitOfWork(run=None)

    with pytest.raises(UnknownAgentRun):
        await _use_case(uow).execute(
            SubmitFeedbackCommand(
                agent_run_id=_RUN_ID, rating=FeedbackRating.UP
            )
        )

    assert not uow.committed
    assert uow.feedback.added == []
