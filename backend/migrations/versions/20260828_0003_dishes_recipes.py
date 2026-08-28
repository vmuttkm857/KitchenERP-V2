"""create dishes and dish recipes

Revision ID: 20260828_0003
Revises: 20260828_0002
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0003"
down_revision: str | None = "20260828_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dishes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["dish_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_dishes"),
        sa.UniqueConstraint("code", name="uq_dishes_code"),
        sa.UniqueConstraint("name", name="uq_dishes_name"),
    )
    op.create_index("ix_dishes_category_id", "dishes", ["category_id"])
    op.create_index("ix_dishes_is_active", "dishes", ["is_active"])

    op.create_table(
        "dish_ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("loss_rate", sa.Numeric(9, 6), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_dish_ingredients_quantity_nonnegative"),
        sa.CheckConstraint("loss_rate >= 0", name="ck_dish_ingredients_loss_rate_nonnegative"),
        sa.CheckConstraint("sort_order >= 0", name="ck_dish_ingredients_sort_order_nonnegative"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_dish_ingredients"),
        sa.UniqueConstraint("dish_id", "ingredient_id", name="uq_dish_ingredients_dish_ingredient"),
    )
    op.create_index("ix_dish_ingredients_dish_id", "dish_ingredients", ["dish_id"])
    op.create_index("ix_dish_ingredients_ingredient_id", "dish_ingredients", ["ingredient_id"])
    op.create_index("ix_dish_ingredients_dish_recipe_order", "dish_ingredients", ["dish_id", "sort_order", "id"])


def downgrade() -> None:
    op.drop_table("dish_ingredients")
    op.drop_table("dishes")
