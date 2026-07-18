"""outbox relay: backoff-колонки и NOTIFY-триггер

Revision ID: 0002_outbox_relay
Revises: 0001_baseline
Create Date: 2026-07-19

Добавляет механику relay: колонки повторных попыток/карантина и
триггер pg_notify (ускоритель пробуждения relay; источник истины —
строки таблицы, поэтому polling остаётся страховкой).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_outbox_relay"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbox ADD COLUMN next_attempt_at TIMESTAMPTZ")
    op.execute("ALTER TABLE outbox ADD COLUMN last_error TEXT")
    op.execute("ALTER TABLE outbox ADD COLUMN failed_at TIMESTAMPTZ")

    op.execute("DROP INDEX IF EXISTS ix_outbox_pending")
    op.execute(
        "CREATE INDEX ix_outbox_pending ON outbox(id) "
        "WHERE published_at IS NULL AND failed_at IS NULL"
    )

    op.execute(
        """
        CREATE FUNCTION notify_outbox() RETURNS trigger AS $$
        BEGIN
          PERFORM pg_notify('catalog_outbox', '');
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_outbox_notify AFTER INSERT ON outbox "
        "FOR EACH STATEMENT EXECUTE FUNCTION notify_outbox()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_outbox_notify ON outbox")
    op.execute("DROP FUNCTION IF EXISTS notify_outbox")
    op.execute("DROP INDEX IF EXISTS ix_outbox_pending")
    op.execute(
        "CREATE INDEX ix_outbox_pending ON outbox(id) "
        "WHERE published_at IS NULL"
    )
    op.execute("ALTER TABLE outbox DROP COLUMN failed_at")
    op.execute("ALTER TABLE outbox DROP COLUMN last_error")
    op.execute("ALTER TABLE outbox DROP COLUMN next_attempt_at")
