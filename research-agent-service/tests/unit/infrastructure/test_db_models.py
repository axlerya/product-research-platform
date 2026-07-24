"""Тесты схемы ORM-моделей (инспекция метаданных, без БД)."""

from research_agent_service.infrastructure.db import models
from research_agent_service.infrastructure.db.base import Base


def test_all_tables_registered() -> None:
    """Зарегистрированы все шесть таблиц."""
    assert models.ConversationORM.__tablename__ == "conversations"
    assert set(Base.metadata.tables) == {
        "conversations",
        "messages",
        "agent_runs",
        "tool_calls",
        "feedback",
        "outbox_events",
    }


def test_agent_runs_columns() -> None:
    """agent_runs несёт ключевые колонки прогона."""
    columns = set(Base.metadata.tables["agent_runs"].columns.keys())

    assert {
        "id",
        "conversation_id",
        "query_message_id",
        "answer_message_id",
        "status",
        "client_principal",
        "idempotency_key",
        "trace_id",
        "correlation_id",
    } <= columns


def test_outbox_columns() -> None:
    """outbox_events несёт колонки жизненного цикла публикации."""
    columns = set(Base.metadata.tables["outbox_events"].columns.keys())

    assert {
        "id",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "payload",
        "headers",
        "published_at",
        "attempts",
        "next_attempt_at",
        "last_error",
        "failed_at",
    } <= columns


def test_foreign_keys_point_to_parents() -> None:
    """messages ссылается на conversations по FK."""
    targets = {
        fk.column.table.name
        for fk in Base.metadata.tables["messages"].foreign_keys
    }

    assert "conversations" in targets
