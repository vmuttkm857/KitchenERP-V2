"""persist ordering adjustment display units

Revision ID: 20261008_0027
Revises: 20261007_0026
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0027"
down_revision = "20261007_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ordering_adjustment_lines", sa.Column("adjusted_unit", sa.String(30), nullable=True))
    op.execute("UPDATE ordering_adjustment_lines SET adjusted_unit = system_unit WHERE adjusted_quantity IS NOT NULL")
    op.create_check_constraint(
        "ck_ordering_adjustment_lines_adjusted_pair",
        "ordering_adjustment_lines",
        "(adjusted_quantity IS NULL) = (adjusted_unit IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ordering_adjustment_lines_adjusted_pair", "ordering_adjustment_lines", type_="check")
    op.drop_column("ordering_adjustment_lines", "adjusted_unit")
