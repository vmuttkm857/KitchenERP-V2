import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class PostpartumCase(AuditColumns, Base):
    __tablename__ = "postpartum_cases"
    __table_args__ = (
        CheckConstraint("delivery_type IN ('vaginal','cesarean')", name="ck_postpartum_cases_delivery_type"),
        CheckConstraint("service_start_meal IN ('breakfast','lunch','dinner')", name="ck_postpartum_cases_start_meal"),
        CheckConstraint("service_end_meal IS NULL OR service_end_meal IN ('breakfast','lunch','dinner')", name="ck_postpartum_cases_end_meal"),
        CheckConstraint("(service_end_date IS NULL) = (service_end_meal IS NULL)", name="ck_postpartum_cases_end_pair"),
        CheckConstraint("service_end_date IS NULL OR service_end_date >= service_start_date", name="ck_postpartum_cases_date_range"),
        CheckConstraint("status IN ('pending','active','paused','ended')", name="ck_postpartum_cases_status"),
        CheckConstraint("preparation_mode IN ('no_herbal','herbal','rice_wine_sesame','no_rice_wine_sesame')", name="ck_postpartum_cases_preparation_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    current_room: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    delivery_type: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    service_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_start_meal: Mapped[str] = mapped_column(String(20), nullable=False)
    service_end_date: Mapped[date | None] = mapped_column(Date)
    service_end_meal: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    preparation_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    service_note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)


class PostpartumRoomHistory(AuditColumns, Base):
    __tablename__ = "postpartum_room_histories"
    __table_args__ = (
        CheckConstraint("effective_meal IN ('breakfast','lunch','dinner')", name="ck_postpartum_room_histories_meal"),
        Index("ix_postpartum_room_histories_case_effective", "case_id", "effective_date", "effective_meal", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("postpartum_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    room: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_meal: Mapped[str] = mapped_column(String(20), nullable=False)


class PostpartumServicePause(AuditColumns, Base):
    __tablename__ = "postpartum_service_pauses"
    __table_args__ = (
        CheckConstraint("start_meal IN ('breakfast','lunch','dinner')", name="ck_postpartum_service_pauses_start_meal"),
        CheckConstraint("end_meal IN ('breakfast','lunch','dinner')", name="ck_postpartum_service_pauses_end_meal"),
        CheckConstraint("end_date >= start_date", name="ck_postpartum_service_pauses_date_range"),
        Index("ix_postpartum_service_pauses_case_start", "case_id", "start_date", "start_meal", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("postpartum_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_meal: Mapped[str] = mapped_column(String(20), nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_meal: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class PostpartumRestrictionGroup(AuditColumns, Base):
    __tablename__ = "postpartum_restriction_groups"
    __table_args__ = (
        Index("uq_postpartum_restriction_groups_name_normalized", text("lower(btrim(name))"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)


class PostpartumRestrictionGroupIngredient(Base):
    __tablename__ = "postpartum_restriction_group_ingredients"

    restriction_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postpartum_restriction_groups.id", ondelete="CASCADE"), primary_key=True,
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="RESTRICT"), primary_key=True, index=True,
    )


class PostpartumRestrictionGroupDish(Base):
    __tablename__ = "postpartum_restriction_group_dishes"

    restriction_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postpartum_restriction_groups.id", ondelete="CASCADE"), primary_key=True,
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), primary_key=True, index=True,
    )
