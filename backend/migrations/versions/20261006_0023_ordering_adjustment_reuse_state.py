"""persist ordering adjustment reuse state

Revision ID: 20261006_0023
Revises: 20261006_0022
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261006_0023"
down_revision = "20261006_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ordering_adjustment_sheets",sa.Column("last_reuse_source_sheet_id",postgresql.UUID(as_uuid=True)))
    op.add_column("ordering_adjustment_sheets",sa.Column("reuse_applied_at",sa.DateTime(timezone=True)))
    op.add_column("ordering_adjustment_sheets",sa.Column("reuse_applied_by",postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_ordering_adjustment_sheets_reuse_applied_by_users","ordering_adjustment_sheets","users",["reuse_applied_by"],["id"],ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_ordering_adjustment_sheets_reuse_applied_by_users","ordering_adjustment_sheets",type_="foreignkey")
    op.drop_column("ordering_adjustment_sheets","reuse_applied_by")
    op.drop_column("ordering_adjustment_sheets","reuse_applied_at")
    op.drop_column("ordering_adjustment_sheets","last_reuse_source_sheet_id")
