"""ORM-модели SQLAlchemy 2.0 — персистентные строки таблиц.

Это НЕ доменные сущности: анемичные модели-таблицы. Домен о них не знает;
связь — через ручной Data Mapper (см. ``mappers.py``). Чанки job и элементы
команды хранятся как JSONB (порядок значим). Индексы/uq/fk задаются здесь и
переносятся в миграцию Alembic вручную.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from indexing_service.infrastructure.db.base import (
    Base,
    sha256_hex,
    ts_tz,
    uuid_pk,
)


class IndexingJobORM(Base):
    """Таблица заданий индексации (агрегат ``IndexingJob``)."""

    __tablename__ = "indexing_jobs"

    job_id: Mapped[uuid_pk]
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    sku: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[sha256_hex] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_collection: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    chunks: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())
    updated_at: Mapped[ts_tz] = mapped_column()
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("product_id", "content_version"),
        CheckConstraint("aggregate_version >= 1", name="aggregate_version_min"),
        CheckConstraint("content_version >= 1", name="content_version_min"),
    )


class EmbeddingRequestORM(Base):
    """Таблица команд на эмбеддинг (дочерних к job)."""

    __tablename__ = "embedding_requests"

    request_id: Mapped[uuid_pk]
    job_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("indexing_jobs.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    items: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())
    requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("attempt >= 0", name="attempt_non_negative"),
    )


class OutboxORM(Base):
    """Таблица transactional outbox (команды на эмбеддинг)."""

    __tablename__ = "outbox"

    id: Mapped[uuid_pk]
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    occurred_at: Mapped[ts_tz] = mapped_column()
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
