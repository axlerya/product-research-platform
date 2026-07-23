"""Эпоха reindex: уникальность job с учётом целевой коллекции.

Revision ID: 0002_reindex_epoch
Revises: 0001_baseline

Уникальность ``(product_id, content_version)`` не давала завести задание на
ту же версию текста в НОВОЙ коллекции: reindex дедуплицировался о задания
живого alias'а и не ставил ни одного. Расширяем ключ целевой коллекцией.

``target_collection IS NULL`` означает «пишем в alias», поэтому в индексе
берём ``COALESCE(target_collection, '')`` — иначе NULL'ы считались бы
различными и дедуп alias-пути перестал бы работать вовсе.
"""

from alembic import op

revision = "0002_reindex_epoch"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE indexing_jobs "
        "DROP CONSTRAINT uq_indexing_jobs_product_id_content_version"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_indexing_jobs_product_version_target "
        "ON indexing_jobs "
        "(product_id, content_version, COALESCE(target_collection, ''))"
    )
    # Прогресс эпохи: сколько заданий коллекции в каком статусе.
    op.execute(
        "CREATE INDEX ix_indexing_jobs_target_collection "
        "ON indexing_jobs(target_collection, status) "
        "WHERE target_collection IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_indexing_jobs_target_collection")
    op.execute("DROP INDEX uq_indexing_jobs_product_version_target")
    op.execute(
        "ALTER TABLE indexing_jobs "
        "ADD CONSTRAINT uq_indexing_jobs_product_id_content_version "
        "UNIQUE (product_id, content_version)"
    )
