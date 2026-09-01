"""add nutrition foundation and ingredient mapping

Revision ID: 20260901_0010
Revises: 20260831_0009
Create Date: 2026-09-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0010"
down_revision: str | None = "20260831_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nutrition_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("version_label", sa.String(150), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("imported_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["imported_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_nutrition_import_batches"),
    )
    op.create_index("ix_nutrition_import_batches_imported_at", "nutrition_import_batches", ["imported_at"])
    op.create_table(
        "nutrition_nutrients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("basis", sa.String(30), server_default="per_100_g", nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("original_source_name", sa.String(250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_nutrition_nutrients"),
        sa.UniqueConstraint("code", name="uq_nutrition_nutrients_code"),
    )
    op.create_table(
        "nutrition_foods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("external_code", sa.String(100), nullable=True),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("category", sa.String(150), nullable=True),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=True),
        sa.Column("waste_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("brand", sa.String(200), nullable=True),
        sa.Column("source_note", sa.String(1000), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("active_in_latest_import", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("last_import_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("(source = 'tfda' AND external_code IS NOT NULL) OR source = 'manual'", name="ck_nutrition_foods_source_code"),
        sa.CheckConstraint("source IN ('tfda', 'manual')", name="ck_nutrition_foods_source"),
        sa.ForeignKeyConstraint(["last_import_batch_id"], ["nutrition_import_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_nutrition_foods"),
        sa.UniqueConstraint("source", "external_code", name="uq_nutrition_foods_source_external_code"),
    )
    op.create_index("ix_nutrition_foods_source_active", "nutrition_foods", ["source", "is_active", "active_in_latest_import"])
    op.create_index("ix_nutrition_foods_category", "nutrition_foods", ["category"])
    op.create_table(
        "nutrition_food_values",
        sa.Column("food_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nutrient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Numeric(24, 10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["food_id"], ["nutrition_foods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["nutrient_id"], ["nutrition_nutrients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("food_id", "nutrient_id", name="pk_nutrition_food_values"),
    )
    op.add_column("ingredients", sa.Column("nutrition_food_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_ingredients_nutrition_food_id", "ingredients", "nutrition_foods", ["nutrition_food_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_ingredients_nutrition_food_id", "ingredients", ["nutrition_food_id"])


def downgrade() -> None:
    op.drop_index("ix_ingredients_nutrition_food_id", table_name="ingredients")
    op.drop_constraint("fk_ingredients_nutrition_food_id", "ingredients", type_="foreignkey")
    op.drop_column("ingredients", "nutrition_food_id")
    op.drop_table("nutrition_food_values")
    op.drop_table("nutrition_foods")
    op.drop_table("nutrition_nutrients")
    op.drop_table("nutrition_import_batches")
