"""add menu meal type columns

Revision ID: 20260903_0013
Revises: 20260901_0012
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0013"
down_revision: str | None = "20260901_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "menu_meal_type_columns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_meal_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("sort_order >= 1", name="ck_menu_meal_type_columns_sort_order_positive"),
        sa.ForeignKeyConstraint(["menu_meal_type_id"], ["menu_meal_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_menu_meal_type_columns"),
        sa.UniqueConstraint("menu_meal_type_id", "name", name="uq_menu_meal_type_columns_meal_name"),
    )
    op.create_index("ix_menu_meal_type_columns_menu_meal_type_id", "menu_meal_type_columns", ["menu_meal_type_id"])
    op.create_index("ix_menu_meal_type_columns_meal_order", "menu_meal_type_columns", ["menu_meal_type_id", "sort_order", "id"])


def downgrade() -> None:
    op.drop_index("ix_menu_meal_type_columns_meal_order", table_name="menu_meal_type_columns")
    op.drop_index("ix_menu_meal_type_columns_menu_meal_type_id", table_name="menu_meal_type_columns")
    op.drop_table("menu_meal_type_columns")
