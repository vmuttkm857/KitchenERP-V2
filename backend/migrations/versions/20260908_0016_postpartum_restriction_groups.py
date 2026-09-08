"""add postpartum restriction groups

Revision ID: 20260908_0016
Revises: 20260908_0015
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0016"
down_revision = "20260908_0015"
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
    ]


def upgrade():
    op.create_table(
        "postpartum_restriction_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *audit_columns(),
    )
    op.create_index("uq_postpartum_restriction_groups_name_normalized", "postpartum_restriction_groups", [sa.text("lower(btrim(name))")], unique=True)
    op.create_index("ix_postpartum_restriction_groups_is_active", "postpartum_restriction_groups", ["is_active"])
    op.create_table(
        "postpartum_restriction_group_ingredients",
        sa.Column("restriction_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["restriction_group_id"], ["postpartum_restriction_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("restriction_group_id", "ingredient_id"),
    )
    op.create_index("ix_postpartum_restriction_group_ingredients_ingredient_id", "postpartum_restriction_group_ingredients", ["ingredient_id"])
    op.create_table(
        "postpartum_restriction_group_dishes",
        sa.Column("restriction_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["restriction_group_id"], ["postpartum_restriction_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("restriction_group_id", "dish_id"),
    )
    op.create_index("ix_postpartum_restriction_group_dishes_dish_id", "postpartum_restriction_group_dishes", ["dish_id"])


def downgrade():
    op.drop_table("postpartum_restriction_group_dishes")
    op.drop_table("postpartum_restriction_group_ingredients")
    op.drop_table("postpartum_restriction_groups")
