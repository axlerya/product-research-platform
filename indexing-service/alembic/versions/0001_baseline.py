"""baseline: indexing jobs, embedding requests, outbox

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-20

Схема indexing-service: задания индексации (с уникальностью
(product_id, content_version) и чанками в JSONB), команды на эмбеддинг
(дочерние к job) и transactional outbox для публикации команд.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE indexing_jobs (
          job_id            UUID PRIMARY KEY,
          product_id        UUID     NOT NULL,
          sku               TEXT     NOT NULL,
          aggregate_version INTEGER  NOT NULL,
          content_version   INTEGER  NOT NULL,
          content_hash      CHAR(64) NOT NULL,
          action            TEXT     NOT NULL,
          target_collection TEXT,
          expected_model    TEXT,
          status            TEXT     NOT NULL,
          chunks            JSONB    NOT NULL,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at        TIMESTAMPTZ NOT NULL,
          applied_at        TIMESTAMPTZ,
          CONSTRAINT uq_indexing_jobs_product_id_content_version
            UNIQUE (product_id, content_version),
          CONSTRAINT ck_indexing_jobs_aggregate_version_min
            CHECK (aggregate_version >= 1),
          CONSTRAINT ck_indexing_jobs_content_version_min
            CHECK (content_version >= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_indexing_jobs_product_id "
        "ON indexing_jobs(product_id)"
    )
    op.execute(
        "CREATE INDEX ix_indexing_jobs_status ON indexing_jobs(status) "
        "WHERE status IN ('awaiting', 'partially_failed')"
    )

    op.execute(
        """
        CREATE TABLE embedding_requests (
          request_id      UUID PRIMARY KEY,
          job_id          UUID    NOT NULL,
          attempt         INTEGER NOT NULL,
          items           JSONB   NOT NULL,
          status          TEXT    NOT NULL,
          next_attempt_at TIMESTAMPTZ,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          requested_at    TIMESTAMPTZ,
          received_at     TIMESTAMPTZ,
          CONSTRAINT fk_embedding_requests_job_id_indexing_jobs
            FOREIGN KEY (job_id) REFERENCES indexing_jobs(job_id)
            ON DELETE CASCADE,
          CONSTRAINT ck_embedding_requests_attempt_non_negative
            CHECK (attempt >= 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_embedding_requests_job_id "
        "ON embedding_requests(job_id)"
    )
    op.execute(
        "CREATE INDEX ix_embedding_requests_due "
        "ON embedding_requests(next_attempt_at) "
        "WHERE status = 'pending' AND next_attempt_at IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE outbox (
          id              UUID PRIMARY KEY,
          aggregate_type  TEXT    NOT NULL,
          aggregate_id    UUID    NOT NULL,
          event_type      TEXT    NOT NULL,
          payload         JSONB   NOT NULL,
          headers         JSONB   NOT NULL DEFAULT '{}'::jsonb,
          occurred_at     TIMESTAMPTZ NOT NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          published_at    TIMESTAMPTZ,
          attempts        INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TIMESTAMPTZ,
          last_error      TEXT,
          failed_at       TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_outbox_pending ON outbox(id) "
        "WHERE published_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_outbox_aggregate ON outbox(aggregate_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outbox")
    op.execute("DROP TABLE IF EXISTS embedding_requests")
    op.execute("DROP TABLE IF EXISTS indexing_jobs")
