"""add ordering adjustment sheets and source lines

Revision ID: 20261002_0021
Revises: 20260911_0020
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261002_0021"
down_revision = "20260911_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_snapshots_criteria_content", "requirement_snapshots", type_="unique")
    op.add_column("requirement_snapshots", sa.Column("snapshot_kind", sa.String(32), server_default="standard", nullable=False))
    op.create_check_constraint("ck_requirement_snapshots_kind", "requirement_snapshots", "snapshot_kind IN ('standard','ordering_adjustment')")
    op.create_index("uq_requirement_snapshots_standard_content", "requirement_snapshots", ["criteria_fingerprint", "content_fingerprint"], unique=True, postgresql_where=sa.text("snapshot_kind = 'standard'"))
    op.create_table(
        "ordering_adjustment_sheets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("baseline_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("criteria_fingerprint", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("status IN ('draft','confirmed','cancelled')", name="ck_ordering_adjustment_sheets_status"),
        sa.CheckConstraint("revision >= 1", name="ck_ordering_adjustment_sheets_revision_positive"),
        sa.CheckConstraint("lock_version >= 1", name="ck_ordering_adjustment_sheets_lock_version_positive"),
        sa.ForeignKeyConstraint(["baseline_snapshot_id"], ["requirement_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("baseline_snapshot_id", name="uq_ordering_adjustment_sheets_snapshot"),
    )
    op.create_index("ix_ordering_adjustment_sheets_status", "ordering_adjustment_sheets", ["status"])
    op.create_index("ix_ordering_adjustment_sheets_created_at", "ordering_adjustment_sheets", ["created_at"])
    op.create_index("uq_ordering_adjustment_sheets_active_source", "ordering_adjustment_sheets", ["criteria_fingerprint", "source_fingerprint"], unique=True, postgresql_where=sa.text("status = 'draft'"))

    op.create_table(
        "ordering_adjustment_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sheet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_line_key", sa.String(80), nullable=False),
        sa.Column("source_signature", sa.String(64), nullable=False),
        sa.Column("source_menu_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_name_snapshot", sa.String(150), nullable=False),
        sa.Column("source_menu_day_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_date", sa.Date(), nullable=False),
        sa.Column("source_meal_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meal_type_name_snapshot", sa.String(100), nullable=False),
        sa.Column("meal_type_sort_order_snapshot", sa.Integer(), nullable=False),
        sa.Column("source_menu_meal_type_column_id", postgresql.UUID(as_uuid=True)),
        sa.Column("menu_meal_type_column_sort_order_snapshot", sa.Integer()),
        sa.Column("source_menu_dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_dish_sort_order_snapshot", sa.Integer(), nullable=False),
        sa.Column("source_dish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dish_code_snapshot", sa.String(50), nullable=False),
        sa.Column("dish_name_snapshot", sa.String(150), nullable=False),
        sa.Column("diner_count_snapshot", sa.Integer(), nullable=False),
        sa.Column("source_dish_ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dish_ingredient_sort_order_snapshot", sa.Integer(), nullable=False),
        sa.Column("source_ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_code_snapshot", sa.String(50), nullable=False),
        sa.Column("ingredient_name_snapshot", sa.String(150), nullable=False),
        sa.Column("source_supplier_id", postgresql.UUID(as_uuid=True)),
        sa.Column("supplier_name_snapshot", sa.String(150)),
        sa.Column("quantity_per_person_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("loss_rate_snapshot", sa.Numeric(9, 6), nullable=False),
        sa.Column("recipe_unit_snapshot", sa.String(30), nullable=False),
        sa.Column("ingredient_base_unit_snapshot", sa.String(30), nullable=False),
        sa.Column("configured_purchase_unit_snapshot", sa.String(30)),
        sa.Column("package_size_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("minimum_order_quantity_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("current_price_snapshot", sa.Numeric(18, 4)),
        sa.Column("system_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("system_unit", sa.String(30), nullable=False),
        sa.Column("adjusted_quantity", sa.Numeric(18, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("diner_count_snapshot >= 0", name="ck_ordering_adjustment_lines_diners_nonnegative"),
        sa.CheckConstraint("quantity_per_person_snapshot >= 0", name="ck_ordering_adjustment_lines_per_person_nonnegative"),
        sa.CheckConstraint("loss_rate_snapshot >= 0", name="ck_ordering_adjustment_lines_loss_nonnegative"),
        sa.CheckConstraint("system_quantity >= 0", name="ck_ordering_adjustment_lines_system_nonnegative"),
        sa.CheckConstraint("adjusted_quantity IS NULL OR adjusted_quantity >= 0", name="ck_ordering_adjustment_lines_adjusted_nonnegative"),
        sa.ForeignKeyConstraint(["sheet_id"], ["ordering_adjustment_sheets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_item_id"], ["requirement_snapshot_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("sheet_id", "source_menu_dish_id", "source_dish_ingredient_id", name="uq_ordering_adjustment_lines_source"),
        sa.UniqueConstraint("sheet_id", "source_line_key", name="uq_ordering_adjustment_lines_key"),
    )
    op.create_index("ix_ordering_adjustment_lines_sheet_id", "ordering_adjustment_lines", ["sheet_id"])
    op.create_index("ix_ordering_adjustment_lines_snapshot_item_id", "ordering_adjustment_lines", ["snapshot_item_id"])
    op.create_index("ix_ordering_adjustment_lines_menu_date", "ordering_adjustment_lines", ["source_menu_id", "requirement_date"])


def downgrade() -> None:
    op.drop_table("ordering_adjustment_lines")
    op.drop_table("ordering_adjustment_sheets")
    inspector=sa.inspect(op.get_bind())
    snapshot_columns={column["name"] for column in inspector.get_columns("requirement_snapshots")}
    if "snapshot_kind" in snapshot_columns:
        op.execute("DELETE FROM requirement_snapshots WHERE snapshot_kind = 'ordering_adjustment'")
        op.drop_index("uq_requirement_snapshots_standard_content", table_name="requirement_snapshots")
        op.drop_constraint("ck_requirement_snapshots_kind", "requirement_snapshots", type_="check")
        op.drop_column("requirement_snapshots", "snapshot_kind")
        op.create_unique_constraint("uq_snapshots_criteria_content", "requirement_snapshots", ["criteria_fingerprint", "content_fingerprint"])
