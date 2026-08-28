import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,Index,Numeric,String,Text,UniqueConstraint,func
from sqlalchemy.dialects.postgresql import JSONB,UUID
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class PurchaseBatch(Base):
    __tablename__="purchase_batches"
    __table_args__=(CheckConstraint("status IN ('draft','confirmed','cancelled')",name="ck_purchase_batches_status"),UniqueConstraint("source_snapshot_id",name="uq_purchase_batches_source_snapshot"),UniqueConstraint("purchase_number",name="uq_purchase_batches_number"),Index("ix_purchase_batches_created_at","created_at"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    purchase_number:Mapped[str]=mapped_column(String(40),nullable=False)
    source_snapshot_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("requirement_snapshots.id",ondelete="RESTRICT"),nullable=False,index=True)
    source_snapshot_revision:Mapped[int]=mapped_column(nullable=False)
    source_summary_snapshot:Mapped[list]=mapped_column(JSONB,nullable=False)
    status:Mapped[str]=mapped_column(String(16),nullable=False,default="draft",server_default="draft",index=True)
    known_total_cost:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    total_cost:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    anomaly_snapshot:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    notes:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now(),onupdate=func.now())
    created_by:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),nullable=False,index=True)
    updated_by:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),nullable=False)
    confirmed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));cancelled_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class PurchaseOrder(Base):
    __tablename__="purchase_orders"
    __table_args__=(UniqueConstraint("batch_id","supplier_id",name="uq_purchase_orders_batch_supplier"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    batch_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("purchase_batches.id",ondelete="CASCADE"),nullable=False,index=True)
    supplier_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),nullable=False)
    supplier_code_snapshot:Mapped[str|None]=mapped_column(String(50));supplier_name_snapshot:Mapped[str]=mapped_column(String(150),nullable=False)
    known_total_cost:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False);total_cost:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class PurchaseOrderItem(Base):
    __tablename__="purchase_order_items"
    __table_args__=(CheckConstraint("final_purchase_quantity >= 0",name="ck_purchase_items_final_quantity_nonnegative"),UniqueConstraint("purchase_order_id","source_snapshot_item_id",name="uq_purchase_items_order_source_item"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    purchase_order_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("purchase_orders.id",ondelete="CASCADE"),nullable=False,index=True)
    source_snapshot_item_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),nullable=False)
    ingredient_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True));ingredient_code_snapshot:Mapped[str]=mapped_column(String(50),nullable=False);ingredient_name_snapshot:Mapped[str]=mapped_column(String(150),nullable=False)
    supplier_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),nullable=False);supplier_code_snapshot:Mapped[str|None]=mapped_column(String(50));supplier_name_snapshot:Mapped[str]=mapped_column(String(150),nullable=False)
    requirement_quantity_snapshot:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False);requirement_unit_snapshot:Mapped[str]=mapped_column(String(20),nullable=False)
    suggested_quantity_snapshot:Mapped[Decimal|None]=mapped_column(Numeric(18,6));adjusted_quantity_snapshot:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    final_purchase_quantity:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False);purchase_unit_snapshot:Mapped[str]=mapped_column(String(20),nullable=False)
    package_size_snapshot:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False);minimum_order_quantity_snapshot:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    unit_price_snapshot:Mapped[Decimal|None]=mapped_column(Numeric(18,6));purchase_cost_snapshot:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    anomaly_snapshot:Mapped[list]=mapped_column(JSONB,nullable=False,default=list);source_summary_snapshot:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
