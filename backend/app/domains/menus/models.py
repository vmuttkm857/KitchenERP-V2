import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class Menu(AuditColumns, Base):
    __tablename__ = "menus"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_menus_date_range"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_categories.id", ondelete="RESTRICT"), index=True)
    notes: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)


class MenuMealType(AuditColumns, Base):
    __tablename__ = "menu_meal_types"
    __table_args__ = (
        UniqueConstraint("menu_id", "name", name="uq_menu_meal_types_menu_name"),
        CheckConstraint("sort_order >= 1", name="ck_menu_meal_types_sort_order_positive"),
        Index("ix_menu_meal_types_menu_order", "menu_id", "sort_order", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class MenuDay(AuditColumns, Base):
    __tablename__ = "menu_days"
    __table_args__ = (
        UniqueConstraint("menu_id", "menu_date", "menu_meal_type_id", name="uq_menu_days_menu_date_meal_type"),
        Index("ix_menu_days_menu_date", "menu_id", "menu_date", "menu_meal_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False, index=True)
    menu_date: Mapped[date] = mapped_column(Date, nullable=False)
    menu_meal_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_meal_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(String(1000))


class MenuDish(AuditColumns, Base):
    __tablename__ = "menu_dishes"
    __table_args__ = (
        UniqueConstraint("menu_day_id", "dish_id", name="uq_menu_dishes_day_dish"),
        CheckConstraint("diner_count >= 0", name="ck_menu_dishes_diner_count_nonnegative"),
        CheckConstraint("sort_order >= 1", name="ck_menu_dishes_sort_order_positive"),
        Index("ix_menu_dishes_day_sort", "menu_day_id", "sort_order", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_day_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_days.id", ondelete="RESTRICT"), nullable=False, index=True)
    dish_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True)
    diner_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    notes: Mapped[str | None] = mapped_column(String(1000))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
