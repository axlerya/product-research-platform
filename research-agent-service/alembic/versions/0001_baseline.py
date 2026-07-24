"""базовая схема

Revision ID: 0001
Revises:
Create Date: 2026-07-24 21:40:59.550308
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('conversations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=True),
    sa.Column('message_count', sa.Integer(), nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_table('outbox_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('aggregate_type', sa.String(length=64), nullable=False),
    sa.Column('aggregate_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=128), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('headers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('occurred_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('published_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('failed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_events'))
    )
    op.create_index(op.f('ix_outbox_events_aggregate_id'), 'outbox_events', ['aggregate_id'], unique=False)
    op.create_table('agent_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('query_message_id', sa.UUID(), nullable=False),
    sa.Column('answer_message_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('client_principal', sa.String(length=255), nullable=True),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('prompt_version', sa.String(length=32), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('loop_steps', sa.Integer(), nullable=False),
    sa.Column('tool_call_count', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=True),
    sa.Column('degradations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    sa.Column('trace_id', sa.String(length=255), nullable=True),
    sa.Column('correlation_id', sa.String(length=255), nullable=True),
    sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_agent_runs_conversation_id_conversations'), initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_runs'))
    )
    op.create_index(op.f('ix_agent_runs_conversation_id'), 'agent_runs', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_status'), 'agent_runs', ['status'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=True),
    sa.Column('agent_run_id', sa.UUID(), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_created_at'), 'messages', ['created_at'], unique=False)
    op.create_table('feedback',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('agent_run_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('rating', sa.String(length=8), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], name=op.f('fk_feedback_agent_run_id_agent_runs'), initially='DEFERRED', deferrable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_feedback_conversation_id_conversations'), initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_feedback'))
    )
    op.create_index(op.f('ix_feedback_agent_run_id'), 'feedback', ['agent_run_id'], unique=False)
    op.create_table('tool_calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('agent_run_id', sa.UUID(), nullable=False),
    sa.Column('step_index', sa.Integer(), nullable=False),
    sa.Column('tool', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('arguments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], name=op.f('fk_tool_calls_agent_run_id_agent_runs'), initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tool_calls'))
    )
    op.create_index(op.f('ix_tool_calls_agent_run_id'), 'tool_calls', ['agent_run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tool_calls_agent_run_id'), table_name='tool_calls')
    op.drop_table('tool_calls')
    op.drop_index(op.f('ix_feedback_agent_run_id'), table_name='feedback')
    op.drop_table('feedback')
    op.drop_index(op.f('ix_messages_created_at'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_agent_runs_status'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_conversation_id'), table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_index(op.f('ix_outbox_events_aggregate_id'), table_name='outbox_events')
    op.drop_table('outbox_events')
    op.drop_table('conversations')
