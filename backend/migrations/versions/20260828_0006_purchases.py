"""snapshot revisions and purchases

Revision ID: 20260828_0006
Revises: 20260828_0005
"""
from collections.abc import Sequence
import hashlib,json
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision="20260828_0006";down_revision="20260828_0005";branch_labels:Sequence[str]|None=None;depends_on:Sequence[str]|None=None

def _normalize(value):
    if isinstance(value,dict):return {key:_normalize(value[key]) for key in sorted(value)}
    if isinstance(value,list):return sorted((_normalize(item) for item in value),key=lambda item:json.dumps(item,sort_keys=True,separators=(",",":")))
    if isinstance(value,Decimal):return format(value.normalize(),"f")
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,UUID):return str(value)
    return value
def _hash(value):return hashlib.sha256(json.dumps(_normalize(value),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def upgrade():
    op.add_column("requirement_snapshots",sa.Column("criteria_fingerprint",sa.String(64)))
    op.add_column("requirement_snapshots",sa.Column("content_fingerprint",sa.String(64)))
    op.add_column("requirement_snapshots",sa.Column("revision",sa.Integer()))
    op.add_column("requirement_snapshot_items",sa.Column("configured_purchase_unit_snapshot",sa.String(20)))
    bind=op.get_bind();headers=bind.execute(sa.text("SELECT * FROM requirement_snapshots ORDER BY created_at,id")).mappings().all()
    revisions={}
    for header in headers:
        criteria_hash=_hash({"calculation_version":"requirements-v1","criteria":header["criteria"]})
        revisions[criteria_hash]=revisions.get(criteria_hash,0)+1
        items=bind.execute(sa.text("SELECT * FROM requirement_snapshot_items WHERE snapshot_id=:id ORDER BY row_key"),{"id":header["id"]}).mappings().all()
        rows=[]
        for item in items:
            rows.append({"row_key":item["row_key"],"ingredient_id":item["ingredient_id"],"ingredient_code":item["ingredient_code_snapshot"],"ingredient_name":item["ingredient_name_snapshot"],"supplier_id":item["supplier_id"],"supplier_code":item["supplier_code_snapshot"],"supplier_name":item["supplier_name_snapshot"],"requirement_quantity":item["requirement_quantity"],"requirement_unit":item["requirement_unit"],"suggested_purchase_quantity":item["suggested_purchase_quantity"],"suggested_purchase_unit":item["suggested_purchase_unit_snapshot"],"configured_purchase_unit":item["purchase_unit_snapshot"],"package_size":item["package_size_snapshot"],"minimum_order_quantity":item["minimum_order_quantity_snapshot"],"current_price":item["unit_price_snapshot"],"estimated_cost":item["estimated_cost_snapshot"],"needs_review":item["needs_review"],"total_diner_count":item["total_diner_count"],"source_count":item["source_count"],"schedules":item["source_summary"]})
        content_hash=_hash({"calculation_version":"requirements-v1","source_menus":header["source_menus"],"rows":rows,"known_estimated_cost":header["known_estimated_cost"],"total_estimated_cost":header["total_estimated_cost"],"anomalies":header["anomaly_snapshot"]})
        bind.execute(sa.text("UPDATE requirement_snapshots SET criteria_fingerprint=:c,content_fingerprint=:x,revision=:r WHERE id=:id"),{"c":criteria_hash,"x":content_hash,"r":revisions[criteria_hash],"id":header["id"]})
    bind.execute(sa.text("UPDATE requirement_snapshot_items SET configured_purchase_unit_snapshot=purchase_unit_snapshot,purchase_unit_snapshot=COALESCE(suggested_purchase_unit_snapshot,requirement_unit)"))
    op.alter_column("requirement_snapshots","criteria_fingerprint",nullable=False);op.alter_column("requirement_snapshots","content_fingerprint",nullable=False);op.alter_column("requirement_snapshots","revision",nullable=False)
    op.drop_constraint("uq_requirement_snapshots_fingerprint","requirement_snapshots",type_="unique")
    op.create_unique_constraint("uq_snapshots_criteria_content","requirement_snapshots",["criteria_fingerprint","content_fingerprint"]);op.create_unique_constraint("uq_snapshots_criteria_revision","requirement_snapshots",["criteria_fingerprint","revision"]);op.create_index("ix_requirement_snapshots_criteria_fingerprint","requirement_snapshots",["criteria_fingerprint"])
    op.create_table("purchase_batches",sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("purchase_number",sa.String(40),nullable=False),sa.Column("source_snapshot_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("source_snapshot_revision",sa.Integer(),nullable=False),sa.Column("source_summary_snapshot",postgresql.JSONB(),nullable=False),sa.Column("status",sa.String(16),server_default="draft",nullable=False),sa.Column("known_total_cost",sa.Numeric(18,6),nullable=False),sa.Column("total_cost",sa.Numeric(18,6)),sa.Column("anomaly_snapshot",postgresql.JSONB(),nullable=False),sa.Column("notes",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.Column("created_by",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("updated_by",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("confirmed_at",sa.DateTime(timezone=True)),sa.Column("cancelled_at",sa.DateTime(timezone=True)),sa.CheckConstraint("status IN ('draft','confirmed','cancelled')",name="ck_purchase_batches_status"),sa.ForeignKeyConstraint(["source_snapshot_id"],["requirement_snapshots.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["created_by"],["users.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["updated_by"],["users.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id",name="pk_purchase_batches"),sa.UniqueConstraint("source_snapshot_id",name="uq_purchase_batches_source_snapshot"),sa.UniqueConstraint("purchase_number",name="uq_purchase_batches_number"))
    for name,columns in (("ix_purchase_batches_source_snapshot_id",["source_snapshot_id"]),("ix_purchase_batches_status",["status"]),("ix_purchase_batches_created_by",["created_by"]),("ix_purchase_batches_created_at",["created_at"])):op.create_index(name,"purchase_batches",columns)
    op.create_table("purchase_orders",sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("batch_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("supplier_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("supplier_code_snapshot",sa.String(50)),sa.Column("supplier_name_snapshot",sa.String(150),nullable=False),sa.Column("known_total_cost",sa.Numeric(18,6),nullable=False),sa.Column("total_cost",sa.Numeric(18,6)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.ForeignKeyConstraint(["batch_id"],["purchase_batches.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id",name="pk_purchase_orders"),sa.UniqueConstraint("batch_id","supplier_id",name="uq_purchase_orders_batch_supplier"));op.create_index("ix_purchase_orders_batch_id","purchase_orders",["batch_id"])
    op.create_table("purchase_order_items",sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("purchase_order_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("source_snapshot_item_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("ingredient_id",postgresql.UUID(as_uuid=True)),sa.Column("ingredient_code_snapshot",sa.String(50),nullable=False),sa.Column("ingredient_name_snapshot",sa.String(150),nullable=False),sa.Column("supplier_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("supplier_code_snapshot",sa.String(50)),sa.Column("supplier_name_snapshot",sa.String(150),nullable=False),sa.Column("requirement_quantity_snapshot",sa.Numeric(18,6),nullable=False),sa.Column("requirement_unit_snapshot",sa.String(20),nullable=False),sa.Column("suggested_quantity_snapshot",sa.Numeric(18,6)),sa.Column("adjusted_quantity_snapshot",sa.Numeric(18,6),nullable=False),sa.Column("final_purchase_quantity",sa.Numeric(18,6),nullable=False),sa.Column("purchase_unit_snapshot",sa.String(20),nullable=False),sa.Column("package_size_snapshot",sa.Numeric(18,6),nullable=False),sa.Column("minimum_order_quantity_snapshot",sa.Numeric(18,6),nullable=False),sa.Column("unit_price_snapshot",sa.Numeric(18,6)),sa.Column("purchase_cost_snapshot",sa.Numeric(18,6)),sa.Column("anomaly_snapshot",postgresql.JSONB(),nullable=False),sa.Column("source_summary_snapshot",postgresql.JSONB(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.CheckConstraint("final_purchase_quantity >= 0",name="ck_purchase_items_final_quantity_nonnegative"),sa.ForeignKeyConstraint(["purchase_order_id"],["purchase_orders.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id",name="pk_purchase_order_items"),sa.UniqueConstraint("purchase_order_id","source_snapshot_item_id",name="uq_purchase_items_order_source_item"));op.create_index("ix_purchase_order_items_purchase_order_id","purchase_order_items",["purchase_order_id"])

def downgrade():
    op.drop_table("purchase_order_items");op.drop_table("purchase_orders");op.drop_table("purchase_batches")
    op.drop_index("ix_requirement_snapshots_criteria_fingerprint",table_name="requirement_snapshots");op.drop_constraint("uq_snapshots_criteria_revision","requirement_snapshots",type_="unique");op.drop_constraint("uq_snapshots_criteria_content","requirement_snapshots",type_="unique");op.create_unique_constraint("uq_requirement_snapshots_fingerprint","requirement_snapshots",["fingerprint"])
    op.drop_column("requirement_snapshot_items","configured_purchase_unit_snapshot");op.drop_column("requirement_snapshots","revision");op.drop_column("requirement_snapshots","content_fingerprint");op.drop_column("requirement_snapshots","criteria_fingerprint")
