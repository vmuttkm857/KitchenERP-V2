"""add menu import exclusion and duplicate review state

Revision ID: 20261007_0025
Revises: 20261007_0024
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261007_0025"
down_revision = "20261007_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_import_batches", sa.Column("duplicate_conflict_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("menu_import_batches", sa.Column("excluded_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("menu_import_lines", sa.Column("duplicate_conflict", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("menu_import_lines", sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("menu_import_lines", sa.Column("excluded_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_menu_import_lines_excluded_by_users", "menu_import_lines", "users", ["excluded_by"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("ck_menu_import_lines_resolution_status", "menu_import_lines", type_="check")
    op.create_check_constraint(
        "ck_menu_import_lines_resolution_status", "menu_import_lines",
        "resolution_status IN ('MATCHED','UNMATCHED','AMBIGUOUS','INACTIVE_MATCH','MANUALLY_RESOLVED','EXCLUDED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_menu_import_lines_resolution_status", "menu_import_lines", type_="check")
    op.execute(
        "UPDATE menu_import_lines "
        "SET resolution_status = 'UNMATCHED', review_required = true, dish_id = NULL "
        "WHERE resolution_status = 'EXCLUDED'"
    )
    op.execute(
        "UPDATE menu_import_batches AS batch SET "
        "review_required_count = (SELECT count(*) FROM menu_import_lines AS line "
        "WHERE line.batch_id = batch.id AND line.review_required = true), "
        "status = CASE WHEN EXISTS (SELECT 1 FROM menu_import_lines AS line "
        "WHERE line.batch_id = batch.id AND line.review_required = true) "
        "THEN 'REVIEW_REQUIRED' ELSE batch.status END"
    )
    op.create_check_constraint(
        "ck_menu_import_lines_resolution_status", "menu_import_lines",
        "resolution_status IN ('MATCHED','UNMATCHED','AMBIGUOUS','INACTIVE_MATCH','MANUALLY_RESOLVED')",
    )
    op.drop_constraint("fk_menu_import_lines_excluded_by_users", "menu_import_lines", type_="foreignkey")
    op.drop_column("menu_import_lines", "excluded_by")
    op.drop_column("menu_import_lines", "excluded_at")
    op.drop_column("menu_import_lines", "duplicate_conflict")
    op.drop_column("menu_import_batches", "excluded_count")
    op.drop_column("menu_import_batches", "duplicate_conflict_count")
