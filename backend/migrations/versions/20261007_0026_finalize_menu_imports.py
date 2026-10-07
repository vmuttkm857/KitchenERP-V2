"""finalize menu imports into formal menus

Revision ID: 20261007_0026
Revises: 20261007_0025
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261007_0026"
down_revision = "20261007_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_import_batches", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("menu_import_batches", sa.Column("finalized_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("menu_import_batches", sa.Column("finalized_menu_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_menu_import_batches_finalized_by_users", "menu_import_batches", "users",
        ["finalized_by"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_menu_import_batches_finalized_menu_id_menus", "menu_import_batches", "menus",
        ["finalized_menu_id"], ["id"], ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_menu_import_batches_finalized_menu_id", "menu_import_batches", ["finalized_menu_id"])
    op.create_index("ix_menu_import_batches_finalized_menu_id", "menu_import_batches", ["finalized_menu_id"])
    op.drop_constraint("ck_menu_import_batches_status", "menu_import_batches", type_="check")
    op.create_check_constraint(
        "ck_menu_import_batches_status", "menu_import_batches",
        "status IN ('REVIEW_REQUIRED','READY','FINALIZED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_menu_import_batches_status", "menu_import_batches", type_="check")
    op.execute("UPDATE menu_import_batches SET status='READY' WHERE status='FINALIZED'")
    op.create_check_constraint(
        "ck_menu_import_batches_status", "menu_import_batches",
        "status IN ('REVIEW_REQUIRED','READY')",
    )
    op.drop_index("ix_menu_import_batches_finalized_menu_id", table_name="menu_import_batches")
    op.drop_constraint("uq_menu_import_batches_finalized_menu_id", "menu_import_batches", type_="unique")
    op.drop_constraint("fk_menu_import_batches_finalized_menu_id_menus", "menu_import_batches", type_="foreignkey")
    op.drop_constraint("fk_menu_import_batches_finalized_by_users", "menu_import_batches", type_="foreignkey")
    op.drop_column("menu_import_batches", "finalized_menu_id")
    op.drop_column("menu_import_batches", "finalized_by")
    op.drop_column("menu_import_batches", "finalized_at")
