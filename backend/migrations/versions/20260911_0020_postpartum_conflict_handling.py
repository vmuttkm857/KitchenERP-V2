"""add postpartum replacement groups and conflict handling

Revision ID: 20260911_0020
Revises: 20260909_0019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260911_0020"
down_revision = "20260909_0019"
branch_labels = None
depends_on = None

SIX_MEALS = "'breakfast','morning_snack','lunch','afternoon_snack','dinner','evening_snack'"


def audit_columns():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
    )


def upgrade() -> None:
    op.create_table(
        "postpartum_replacement_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("postpartum_meal", sa.String(30), nullable=False),
        sa.Column("replacement_dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.Text()),
        *audit_columns(),
        sa.CheckConstraint(
            f"postpartum_meal IN ({SIX_MEALS})",
            name="ck_postpartum_replacement_groups_meal",
        ),
        sa.ForeignKeyConstraint(["replacement_dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "id", "target_date", "postpartum_meal",
            name="uq_postpartum_replacement_groups_identity_slot",
        ),
    )
    op.create_index(
        "ix_postpartum_replacement_groups_target", "postpartum_replacement_groups",
        ["target_date", "postpartum_meal", "id"],
    )
    op.create_index(
        "ix_postpartum_replacement_groups_replacement_dish_id",
        "postpartum_replacement_groups", ["replacement_dish_id"],
    )
    op.create_table(
        "postpartum_conflict_handlings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("postpartum_meal", sa.String(30), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_menu_dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("replacement_group_id", postgresql.UUID(as_uuid=True)),
        sa.Column("note", sa.Text()),
        *audit_columns(),
        sa.CheckConstraint(
            f"postpartum_meal IN ({SIX_MEALS})",
            name="ck_postpartum_conflict_handlings_meal",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["postpartum_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["replacement_group_id", "target_date", "postpartum_meal"],
            ["postpartum_replacement_groups.id", "postpartum_replacement_groups.target_date", "postpartum_replacement_groups.postpartum_meal"],
            ondelete="CASCADE",
            name="fk_postpartum_conflict_handlings_group_slot",
        ),
        sa.UniqueConstraint(
            "case_id", "original_menu_dish_id",
            name="uq_postpartum_conflict_handlings_item",
        ),
    )
    op.create_index("ix_postpartum_conflict_handlings_case_id", "postpartum_conflict_handlings", ["case_id"])
    op.create_index("ix_postpartum_conflict_handlings_original_dish_id", "postpartum_conflict_handlings", ["original_dish_id"])
    op.create_index("ix_postpartum_conflict_handlings_original_menu_dish_id", "postpartum_conflict_handlings", ["original_menu_dish_id"])
    op.create_index("ix_postpartum_conflict_handlings_group_id", "postpartum_conflict_handlings", ["replacement_group_id"])
    op.create_index(
        "ix_postpartum_conflict_handlings_target", "postpartum_conflict_handlings",
        ["target_date", "postpartum_meal", "id"],
    )


def downgrade() -> None:
    op.drop_table("postpartum_conflict_handlings")
    op.drop_table("postpartum_replacement_groups")
