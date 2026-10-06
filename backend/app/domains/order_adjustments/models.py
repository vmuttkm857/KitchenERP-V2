import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderingAdjustmentSheet(Base):
    __tablename__ = "ordering_adjustment_sheets"
    __table_args__ = (
        CheckConstraint("status IN ('draft','confirmed','cancelled')", name="ck_ordering_adjustment_sheets_status"),
        CheckConstraint("revision >= 1", name="ck_ordering_adjustment_sheets_revision_positive"),
        CheckConstraint("lock_version >= 1", name="ck_ordering_adjustment_sheets_lock_version_positive"),
        UniqueConstraint("baseline_snapshot_id", name="uq_ordering_adjustment_sheets_snapshot"),
        Index("ix_ordering_adjustment_sheets_status", "status"),
        Index("ix_ordering_adjustment_sheets_created_at", "created_at"),
        Index("uq_ordering_adjustment_sheets_active_source", "criteria_fingerprint", "source_fingerprint", unique=True, postgresql_where=text("status = 'draft'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    baseline_snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requirement_snapshots.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    criteria_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)
    last_reuse_source_sheet_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reuse_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reuse_applied_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class OrderingAdjustmentLine(Base):
    __tablename__ = "ordering_adjustment_lines"
    __table_args__ = (
        CheckConstraint("diner_count_snapshot >= 0", name="ck_ordering_adjustment_lines_diners_nonnegative"),
        CheckConstraint("quantity_per_person_snapshot >= 0", name="ck_ordering_adjustment_lines_per_person_nonnegative"),
        CheckConstraint("loss_rate_snapshot >= 0", name="ck_ordering_adjustment_lines_loss_nonnegative"),
        CheckConstraint("system_quantity >= 0", name="ck_ordering_adjustment_lines_system_nonnegative"),
        CheckConstraint("adjusted_quantity IS NULL OR adjusted_quantity >= 0", name="ck_ordering_adjustment_lines_adjusted_nonnegative"),
        UniqueConstraint("sheet_id", "source_menu_dish_id", "source_dish_ingredient_id", name="uq_ordering_adjustment_lines_source"),
        UniqueConstraint("sheet_id", "source_line_key", name="uq_ordering_adjustment_lines_key"),
        Index("ix_ordering_adjustment_lines_menu_date", "source_menu_id", "requirement_date"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sheet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ordering_adjustment_sheets.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requirement_snapshot_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_line_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    source_menu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    menu_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    source_menu_day_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requirement_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_meal_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    meal_type_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    meal_type_sort_order_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    source_menu_meal_type_column_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    menu_meal_type_column_sort_order_snapshot: Mapped[int | None] = mapped_column(Integer)
    source_menu_dish_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    menu_dish_sort_order_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    source_dish_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dish_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    dish_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    diner_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    source_dish_ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dish_ingredient_sort_order_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ingredient_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    ingredient_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    source_supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    supplier_name_snapshot: Mapped[str | None] = mapped_column(String(150))
    quantity_per_person_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    loss_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    recipe_unit_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    ingredient_base_unit_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    configured_purchase_unit_snapshot: Mapped[str | None] = mapped_column(String(30))
    package_size_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    minimum_order_quantity_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    current_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    system_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    system_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    adjusted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
