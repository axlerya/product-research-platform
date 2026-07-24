"""Тесты контрактов персистентности (OutboxMessage + порты)."""

from datetime import UTC, datetime
from uuid import UUID

from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.application.ports.outbox import OutboxRepository
from research_agent_service.application.ports.repositories import (
    AgentRunRepository,
    ConversationRepository,
    FeedbackRepository,
)
from research_agent_service.application.ports.uow import UnitOfWork


def test_outbox_message_defaults() -> None:
    """OutboxMessage: headers пустые, next_attempt_at None по умолчанию."""
    msg = OutboxMessage(
        id=UUID(int=1),
        aggregate_type="agent_run",
        aggregate_id=UUID(int=2),
        event_type="agent.query.completed.v1",
        payload={"k": "v"},
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert msg.headers == {}
    assert msg.next_attempt_at is None


def test_repository_ports_expose_methods() -> None:
    """Репозитории и outbox определяют ожидаемые методы."""
    assert hasattr(ConversationRepository, "load_history")
    assert hasattr(AgentRunRepository, "list")
    assert hasattr(FeedbackRepository, "add")
    assert hasattr(OutboxRepository, "add_many")


def test_unit_of_work_contract() -> None:
    """UnitOfWork: commit/rollback и репозитории на одной сессии."""
    assert hasattr(UnitOfWork, "commit")
    assert hasattr(UnitOfWork, "rollback")
    assert "outbox" in UnitOfWork.__annotations__
    assert "agent_runs" in UnitOfWork.__annotations__
