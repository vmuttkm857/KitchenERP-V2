"""add postpartum menu sources and meal mappings

Revision ID: 20260909_0019
Revises: 20260909_0018
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260909_0019"
down_revision = "20260909_0018"
branch_labels = None
depends_on = None

SIX_MEALS = "'breakfast','morning_snack','lunch','afternoon_snack','dinner','evening_snack'"


def upgrade() -> None:
    op.create_table(
        "postpartum_menu_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("menu_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("menu_id", name="uq_postpartum_menu_sources_menu_id"),
    )
    op.create_index("ix_postpartum_menu_sources_menu_id", "postpartum_menu_sources", ["menu_id"])
    op.create_table(
        "postpartum_menu_meal_mappings",
        sa.Column("menu_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("postpartum_meal", sa.String(30), nullable=False),
        sa.Column("menu_meal_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            f"postpartum_meal IN ({SIX_MEALS})",
            name="ck_postpartum_menu_meal_mappings_meal",
        ),
        sa.ForeignKeyConstraint(
            ["menu_source_id"], ["postpartum_menu_sources.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["menu_meal_type_id"], ["menu_meal_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("menu_source_id", "postpartum_meal"),
        sa.UniqueConstraint(
            "menu_source_id", "menu_meal_type_id",
            name="uq_postpartum_menu_meal_mappings_source_meal_type",
        ),
    )
    op.create_index(
        "ix_postpartum_menu_meal_mappings_menu_meal_type_id",
        "postpartum_menu_meal_mappings", ["menu_meal_type_id"],
    )


def downgrade() -> None:
    op.drop_table("postpartum_menu_meal_mappings")
    op.drop_table("postpartum_menu_sources")
