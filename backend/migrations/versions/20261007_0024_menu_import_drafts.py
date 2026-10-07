"""add persistent menu import drafts

Revision ID: 20261007_0024
Revises: 20261006_0023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261007_0024"
down_revision = "20261006_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "menu_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("date_count", sa.Integer(), nullable=False),
        sa.Column("meal_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("dish_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("review_required_count", sa.Integer(), nullable=False),
        sa.Column("layout", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("status IN ('REVIEW_REQUIRED','READY')", name="ck_menu_import_batches_status"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_menu_import_batches_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_menu_import_batches_updated_by_users", ondelete="RESTRICT"),
    )
    op.create_index("ix_menu_import_batches_status_updated", "menu_import_batches", ["status", "updated_at"])
    op.create_index(
        "uq_menu_import_batches_active_source",
        "menu_import_batches",
        ["source_hash", "sheet_name", "created_by"],
        unique=True,
        postgresql_where=sa.text("status IN ('REVIEW_REQUIRED','READY')"),
    )

    op.create_table(
        "menu_import_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_key", sa.String(64), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_column", sa.Integer(), nullable=False),
        sa.Column("menu_date", sa.Date(), nullable=False),
        sa.Column("meal_name", sa.Text(), nullable=False),
        sa.Column("meal_sort_order", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False),
        sa.Column("column_sort_order", sa.Integer(), nullable=False),
        sa.Column("original_import_name", sa.Text(), nullable=False),
        sa.Column("normalized_import_name", sa.Text(), nullable=False),
        sa.Column("dish_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("diner_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("resolution_status", sa.String(24), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "resolution_status IN ('MATCHED','UNMATCHED','AMBIGUOUS','INACTIVE_MATCH','MANUALLY_RESOLVED')",
            name="ck_menu_import_lines_resolution_status",
        ),
        sa.CheckConstraint("diner_count >= 0", name="ck_menu_import_lines_diner_count_nonnegative"),
        sa.ForeignKeyConstraint(["batch_id"], ["menu_import_batches.id"], name="fk_menu_import_lines_batch", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_menu_import_lines_dish", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], name="fk_menu_import_lines_resolved_by_users", ondelete="RESTRICT"),
        sa.UniqueConstraint("batch_id", "line_key", name="uq_menu_import_lines_batch_line_key"),
    )
    op.create_index(
        "ix_menu_import_lines_batch_order",
        "menu_import_lines",
        ["batch_id", "menu_date", "meal_sort_order", "column_sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_menu_import_lines_batch_order", table_name="menu_import_lines")
    op.drop_table("menu_import_lines")
    op.drop_index("uq_menu_import_batches_active_source", table_name="menu_import_batches")
    op.drop_index("ix_menu_import_batches_status_updated", table_name="menu_import_batches")
    op.drop_table("menu_import_batches")
