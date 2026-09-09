"""add postpartum case restriction groups

Revision ID: 20260909_0017
Revises: 20260908_0016
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260909_0017"
down_revision = "20260908_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "postpartum_case_restriction_groups",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("restriction_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["postpartum_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["restriction_group_id"], ["postpartum_restriction_groups.id"], ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("case_id", "restriction_group_id"),
    )
    op.create_index(
        "ix_postpartum_case_restriction_groups_restriction_group_id",
        "postpartum_case_restriction_groups",
        ["restriction_group_id"],
    )


def downgrade():
    op.drop_table("postpartum_case_restriction_groups")
