"""create categories suppliers and ingredients

Revision ID: 20260828_0002
Revises: 20260828_0001
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0002"
down_revision: str | None = "20260828_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def actor_columns() -> list[sa.Column]:
    return [
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    ]


def create_category_table(table_name: str) -> None:
    op.create_table(
        table_name,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(), *actor_columns(),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table_name}"),
        sa.UniqueConstraint("name", name=f"uq_{table_name}_name"),
    )
    op.create_index(f"ix_{table_name}_is_active", table_name, ["is_active"])


def upgrade() -> None:
    create_category_table("categories")
    create_category_table("dish_categories")
    create_category_table("menu_categories")

    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("contact_person", sa.String(100)),
        sa.Column("phone", sa.String(50)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(), *actor_columns(),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("code", name="uq_suppliers_code"),
    )
    op.create_index("ix_suppliers_is_active", "suppliers", ["is_active"])

    op.create_table(
        "ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("current_price", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("primary_supplier_id", postgresql.UUID(as_uuid=True)),
        sa.Column("purchase_unit", sa.String(30)),
        sa.Column("package_size", sa.Numeric(18, 6), server_default="1", nullable=False),
        sa.Column("minimum_order_quantity", sa.Numeric(18, 6), server_default="0", nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(), *actor_columns(),
        sa.CheckConstraint("current_price >= 0", name="ck_ingredients_current_price_nonnegative"),
        sa.CheckConstraint("package_size >= 0", name="ck_ingredients_package_size_nonnegative"),
        sa.CheckConstraint("minimum_order_quantity >= 0", name="ck_ingredients_minimum_order_nonnegative"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_ingredients"),
        sa.UniqueConstraint("code", name="uq_ingredients_code"),
    )
    op.create_index("ix_ingredients_category_id", "ingredients", ["category_id"])
    op.create_index("ix_ingredients_primary_supplier_id", "ingredients", ["primary_supplier_id"])
    op.create_index("ix_ingredients_is_active", "ingredients", ["is_active"])

    op.create_table(
        "ingredient_price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True)),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_ingredient_price_history_price_nonnegative"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_ingredient_price_history"),
    )
    op.create_index("ix_ingredient_price_history_ingredient_id", "ingredient_price_history", ["ingredient_id"])
    op.create_index("ix_ingredient_price_history_effective_date", "ingredient_price_history", ["effective_date"])


def downgrade() -> None:
    op.drop_table("ingredient_price_history")
    op.drop_table("ingredients")
    op.drop_table("suppliers")
    op.drop_table("menu_categories")
    op.drop_table("dish_categories")
    op.drop_table("categories")
