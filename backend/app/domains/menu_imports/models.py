import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MenuImportBatch(Base):
    __tablename__ = "menu_import_batches"
    __table_args__ = (
        CheckConstraint("status IN ('REVIEW_REQUIRED','READY','FINALIZED')", name="ck_menu_import_batches_status"),
        UniqueConstraint("finalized_menu_id", name="uq_menu_import_batches_finalized_menu_id"),
        Index("ix_menu_import_batches_status_updated", "status", "updated_at"),
        Index(
            "uq_menu_import_batches_active_source",
            "source_hash", "sheet_name", "created_by",
            unique=True,
            postgresql_where=text("status IN ('REVIEW_REQUIRED','READY')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_count: Mapped[int] = mapped_column(Integer, nullable=False)
    meal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dish_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    excluded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    layout: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    finalized_menu_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menus.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class MenuImportLine(Base):
    __tablename__ = "menu_import_lines"
    __table_args__ = (
        CheckConstraint(
            "resolution_status IN ('MATCHED','UNMATCHED','AMBIGUOUS','INACTIVE_MATCH','MANUALLY_RESOLVED','EXCLUDED')",
            name="ck_menu_import_lines_resolution_status",
        ),
        CheckConstraint("diner_count >= 0", name="ck_menu_import_lines_diner_count_nonnegative"),
        UniqueConstraint("batch_id", "line_key", name="uq_menu_import_lines_batch_line_key"),
        Index("ix_menu_import_lines_batch_order", "batch_id", "menu_date", "meal_sort_order", "column_sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_import_batches.id", ondelete="CASCADE"), nullable=False
    )
    line_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_column: Mapped[int] = mapped_column(Integer, nullable=False)
    menu_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_name: Mapped[str] = mapped_column(Text, nullable=False)
    meal_sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    column_sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    original_import_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_import_name: Mapped[str] = mapped_column(Text, nullable=False)
    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="SET NULL"), nullable=True
    )
    diner_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False)
    duplicate_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excluded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
