"""add append-only audit logs

Revision ID: 20260831_0009
Revises: 20260830_0008
Create Date: 2026-08-31
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0009"
down_revision: str | None = "20260830_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_username", sa.String(100), nullable=False),
        sa.Column("actor_display_name", sa.String(150), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_label", sa.String(250), nullable=True),
        sa.Column("before_data", postgresql.JSONB(), nullable=True),
        sa.Column("after_data", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])
    op.create_index("ix_audit_logs_entity_created", "audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
