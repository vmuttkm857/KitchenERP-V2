"""create requirement snapshots

Revision ID: 20260828_0005
Revises: 20260828_0004
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision="20260828_0005";down_revision="20260828_0004";branch_labels:Sequence[str]|None=None;depends_on:Sequence[str]|None=None

def upgrade():
    op.create_table("requirement_snapshots",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("fingerprint",sa.String(64),nullable=False),
        sa.Column("criteria",postgresql.JSONB(),nullable=False),sa.Column("source_menus",postgresql.JSONB(),nullable=False),
        sa.Column("anomaly_snapshot",postgresql.JSONB(),nullable=False),sa.Column("anomaly_summary",postgresql.JSONB(),nullable=False),
        sa.Column("known_estimated_cost",sa.Numeric(18,6),nullable=False),sa.Column("total_estimated_cost",sa.Numeric(18,6)),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),
        sa.Column("created_by",postgresql.UUID(as_uuid=True),nullable=False),sa.ForeignKeyConstraint(["created_by"],["users.id"],ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id",name="pk_requirement_snapshots"),sa.UniqueConstraint("fingerprint",name="uq_requirement_snapshots_fingerprint"))
    op.create_index("ix_requirement_snapshots_created_at","requirement_snapshots",["created_at"]);op.create_index("ix_requirement_snapshots_created_by","requirement_snapshots",["created_by"])
    op.create_table("requirement_snapshot_items",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("snapshot_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("row_key",sa.String(160),nullable=False),
        sa.Column("ingredient_id",postgresql.UUID(as_uuid=True)),sa.Column("ingredient_code_snapshot",sa.String(50),nullable=False),sa.Column("ingredient_name_snapshot",sa.String(150),nullable=False),
        sa.Column("supplier_id",postgresql.UUID(as_uuid=True)),sa.Column("supplier_code_snapshot",sa.String(50)),sa.Column("supplier_name_snapshot",sa.String(150)),
        sa.Column("requirement_quantity",sa.Numeric(18,6),nullable=False),sa.Column("requirement_unit",sa.String(20),nullable=False),sa.Column("suggested_purchase_quantity",sa.Numeric(18,6)),sa.Column("adjusted_quantity",sa.Numeric(18,6)),
        sa.Column("suggested_purchase_unit_snapshot",sa.String(20)),sa.Column("purchase_unit_snapshot",sa.String(20)),sa.Column("package_size_snapshot",sa.Numeric(18,6),nullable=False),sa.Column("minimum_order_quantity_snapshot",sa.Numeric(18,6),nullable=False),
        sa.Column("unit_price_snapshot",sa.Numeric(18,6)),sa.Column("estimated_cost_snapshot",sa.Numeric(18,6)),sa.Column("needs_review",sa.Boolean(),nullable=False),sa.Column("total_diner_count",sa.Integer(),nullable=False),sa.Column("source_count",sa.Integer(),nullable=False),
        sa.Column("anomaly_snapshot",postgresql.JSONB(),nullable=False),sa.Column("source_summary",postgresql.JSONB(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.Column("updated_by",postgresql.UUID(as_uuid=True),nullable=False),
        sa.CheckConstraint("requirement_quantity >= 0",name="ck_snapshot_items_requirement_nonnegative"),sa.CheckConstraint("suggested_purchase_quantity IS NULL OR suggested_purchase_quantity >= 0",name="ck_snapshot_items_suggested_nonnegative"),sa.CheckConstraint("adjusted_quantity IS NULL OR adjusted_quantity >= 0",name="ck_snapshot_items_adjusted_nonnegative"),
        sa.ForeignKeyConstraint(["snapshot_id"],["requirement_snapshots.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["updated_by"],["users.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id",name="pk_requirement_snapshot_items"),sa.UniqueConstraint("snapshot_id","row_key",name="uq_snapshot_items_snapshot_row_key"))
    op.create_index("ix_requirement_snapshot_items_snapshot_id","requirement_snapshot_items",["snapshot_id"])

def downgrade():
    op.drop_table("requirement_snapshot_items");op.drop_table("requirement_snapshots")
