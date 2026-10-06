"""persist ordering adjustment line review state

Revision ID: 20261006_0022
Revises: 20261002_0021
"""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0022"
down_revision = "20261002_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordering_adjustment_lines",
        sa.Column("review_required", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ordering_adjustment_lines", "review_required")
