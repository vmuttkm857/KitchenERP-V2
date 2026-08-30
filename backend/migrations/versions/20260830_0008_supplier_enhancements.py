"""add supplier address and ordering

Revision ID: 20260830_0008
Revises: 20260830_0007
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0008"
down_revision: str | None = "20260830_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("address", sa.String(length=500), nullable=True))
    op.add_column("suppliers", sa.Column("sort_order", sa.Integer(), nullable=True))
    op.execute(sa.text("""
        WITH ordered_suppliers AS (
            SELECT id, row_number() OVER (ORDER BY created_at, code, id) AS position
            FROM suppliers
        )
        UPDATE suppliers
        SET sort_order = ordered_suppliers.position
        FROM ordered_suppliers
        WHERE suppliers.id = ordered_suppliers.id
    """))
    op.alter_column("suppliers", "sort_order", existing_type=sa.Integer(), nullable=False)
    op.create_index("ix_suppliers_sort_order_code", "suppliers", ["sort_order", "code", "id"])


def downgrade() -> None:
    op.drop_index("ix_suppliers_sort_order_code", table_name="suppliers")
    op.drop_column("suppliers", "sort_order")
    op.drop_column("suppliers", "address")
