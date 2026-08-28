import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class RequirementSnapshot(Base):
    __tablename__="requirement_snapshots"
    __table_args__=(UniqueConstraint("criteria_fingerprint","content_fingerprint",name="uq_snapshots_criteria_content"),UniqueConstraint("criteria_fingerprint","revision",name="uq_snapshots_criteria_revision"),Index("ix_requirement_snapshots_created_at","created_at"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    criteria_fingerprint:Mapped[str]=mapped_column(String(64),nullable=False,index=True)
    content_fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    revision:Mapped[int]=mapped_column(Integer,nullable=False)
    criteria:Mapped[dict]=mapped_column(JSONB,nullable=False)
    source_menus:Mapped[list]=mapped_column(JSONB,nullable=False)
    anomaly_snapshot:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    anomaly_summary:Mapped[dict]=mapped_column(JSONB,nullable=False)
    known_estimated_cost:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    total_estimated_cost:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    created_by:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),nullable=False,index=True)

class RequirementSnapshotItem(Base):
    __tablename__="requirement_snapshot_items"
    __table_args__=(CheckConstraint("requirement_quantity >= 0",name="ck_snapshot_items_requirement_nonnegative"),CheckConstraint("suggested_purchase_quantity IS NULL OR suggested_purchase_quantity >= 0",name="ck_snapshot_items_suggested_nonnegative"),CheckConstraint("adjusted_quantity IS NULL OR adjusted_quantity >= 0",name="ck_snapshot_items_adjusted_nonnegative"),UniqueConstraint("snapshot_id","row_key",name="uq_snapshot_items_snapshot_row_key"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    snapshot_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("requirement_snapshots.id",ondelete="CASCADE"),nullable=False,index=True)
    row_key:Mapped[str]=mapped_column(String(160),nullable=False)
    ingredient_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True))
    ingredient_code_snapshot:Mapped[str]=mapped_column(String(50),nullable=False)
    ingredient_name_snapshot:Mapped[str]=mapped_column(String(150),nullable=False)
    supplier_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True))
    supplier_code_snapshot:Mapped[str|None]=mapped_column(String(50))
    supplier_name_snapshot:Mapped[str|None]=mapped_column(String(150))
    requirement_quantity:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    requirement_unit:Mapped[str]=mapped_column(String(20),nullable=False)
    suggested_purchase_quantity:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    adjusted_quantity:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    suggested_purchase_unit_snapshot:Mapped[str|None]=mapped_column(String(20))
    purchase_unit_snapshot:Mapped[str|None]=mapped_column(String(20))
    configured_purchase_unit_snapshot:Mapped[str|None]=mapped_column(String(20))
    package_size_snapshot:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    minimum_order_quantity_snapshot:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False)
    unit_price_snapshot:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    estimated_cost_snapshot:Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    needs_review:Mapped[bool]=mapped_column(nullable=False)
    total_diner_count:Mapped[int]=mapped_column(Integer,nullable=False)
    source_count:Mapped[int]=mapped_column(Integer,nullable=False)
    anomaly_snapshot:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    source_summary:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now(),onupdate=func.now())
    updated_by:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),nullable=False)
