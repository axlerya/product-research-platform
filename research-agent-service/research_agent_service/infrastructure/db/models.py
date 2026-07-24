"""ORM-модели истории запросов, прогонов и outbox."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from research_agent_service.infrastructure.db.base import Base

_uuid = PgUUID(as_uuid=True)
_ts = TIMESTAMP(timezone=True)


class ConversationORM(Base):
    """Диалог."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(_uuid, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(500))
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(_ts)
    updated_at: Mapped[datetime] = mapped_column(_ts)


class MessageORM(Base):
    """Реплика диалога."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(_uuid, primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        _uuid,
        ForeignKey("conversations.id", deferrable=True, initially="DEFERRED"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    token_count: Mapped[int | None] = mapped_column(Integer)
    agent_run_id: Mapped[UUID | None] = mapped_column(_uuid)
    created_at: Mapped[datetime] = mapped_column(_ts, index=True)


class AgentRunORM(Base):
    """Прогон агента над одним запросом."""

    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(_uuid, primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        _uuid,
        ForeignKey("conversations.id", deferrable=True, initially="DEFERRED"),
        index=True,
    )
    query_message_id: Mapped[UUID] = mapped_column(_uuid)
    answer_message_id: Mapped[UUID | None] = mapped_column(_uuid)
    status: Mapped[str] = mapped_column(String(16), index=True)
    client_principal: Mapped[str | None] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    loop_steps: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str | None] = mapped_column(String(16))
    degradations: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[dict | None] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    trace_id: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(_ts)
    finished_at: Mapped[datetime | None] = mapped_column(_ts)


class ToolCallORM(Base):
    """Вызов инструмента внутри прогона."""

    __tablename__ = "tool_calls"

    id: Mapped[UUID] = mapped_column(_uuid, primary_key=True)
    agent_run_id: Mapped[UUID] = mapped_column(
        _uuid,
        ForeignKey("agent_runs.id", deferrable=True, initially="DEFERRED"),
        index=True,
    )
    step_index: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    provenance: Mapped[list] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(_ts)
    finished_at: Mapped[datetime] = mapped_column(_ts)


class FeedbackORM(Base):
    """Обратная связь по прогону."""

    __tablename__ = "feedback"

    id: Mapped[UUID] = mapped_column(_uuid, primary_key=True)
    agent_run_id: Mapped[UUID] = mapped_column(
        _uuid,
        ForeignKey("agent_runs.id", deferrable=True, initially="DEFERRED"),
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        _uuid,
        ForeignKey("conversations.id", deferrable=True, initially="DEFERRED"),
    )
    rating: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(_ts)


class OutboxEventORM(Base):
    """Событие transactional outbox."""

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(_uuid, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[UUID] = mapped_column(_uuid, index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB)
    headers: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(_ts)
    created_at: Mapped[datetime] = mapped_column(_ts)
    published_at: Mapped[datetime | None] = mapped_column(_ts)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(_ts)
    last_error: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(_ts)
