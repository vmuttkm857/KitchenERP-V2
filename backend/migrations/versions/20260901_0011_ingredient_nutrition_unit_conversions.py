"""add ingredient nutrition unit conversions

Revision ID: 20260901_0011
Revises: 20260901_0010
Create Date: 2026-09-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0011"
down_revision: str | None = "20260901_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingredient_nutrition_unit_conversions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("grams_per_unit", sa.Numeric(24, 10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("grams_per_unit > 0", name="ck_ingredient_nutrition_unit_conversions_grams_positive"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_ingredient_nutrition_unit_conversions"),
        sa.UniqueConstraint("ingredient_id", "unit", name="uq_ingredient_nutrition_unit_conversions_ingredient_unit"),
    )
    op.create_index(
        "ix_ingredient_nutrition_unit_conversions_ingredient_id",
        "ingredient_nutrition_unit_conversions", ["ingredient_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingredient_nutrition_unit_conversions_ingredient_id",
        table_name="ingredient_nutrition_unit_conversions",
    )
    op.drop_table("ingredient_nutrition_unit_conversions")
