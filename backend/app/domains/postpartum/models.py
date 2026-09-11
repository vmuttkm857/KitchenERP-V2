import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.postpartum.meals import meal_check


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class PostpartumCase(AuditColumns, Base):
    __tablename__ = "postpartum_cases"
    __table_args__ = (
        CheckConstraint("delivery_type IN ('vaginal','cesarean')", name="ck_postpartum_cases_delivery_type"),
        CheckConstraint(meal_check("service_start_meal"), name="ck_postpartum_cases_start_meal"),
        CheckConstraint(f"service_end_meal IS NULL OR {meal_check('service_end_meal')}", name="ck_postpartum_cases_end_meal"),
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
        CheckConstraint(meal_check("effective_meal"), name="ck_postpartum_room_histories_meal"),
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
        CheckConstraint(meal_check("start_meal"), name="ck_postpartum_service_pauses_start_meal"),
        CheckConstraint(meal_check("end_meal"), name="ck_postpartum_service_pauses_end_meal"),
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


class PostpartumCaseRestrictionGroup(Base):
    __tablename__ = "postpartum_case_restriction_groups"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postpartum_cases.id", ondelete="CASCADE"), primary_key=True,
    )
    restriction_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postpartum_restriction_groups.id", ondelete="RESTRICT"),
        primary_key=True, index=True,
    )


class PostpartumMenuSource(AuditColumns, Base):
    __tablename__ = "postpartum_menu_sources"
    __table_args__ = (
        UniqueConstraint("menu_id", name="uq_postpartum_menu_sources_menu_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False, index=True,
    )


class PostpartumMenuMealMapping(Base):
    __tablename__ = "postpartum_menu_meal_mappings"
    __table_args__ = (
        CheckConstraint(meal_check("postpartum_meal"), name="ck_postpartum_menu_meal_mappings_meal"),
        UniqueConstraint(
            "menu_source_id", "menu_meal_type_id",
            name="uq_postpartum_menu_meal_mappings_source_meal_type",
        ),
        Index(
            "ix_postpartum_menu_meal_mappings_menu_meal_type_id", "menu_meal_type_id",
        ),
    )

    menu_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postpartum_menu_sources.id", ondelete="CASCADE"), primary_key=True,
    )
    postpartum_meal: Mapped[str] = mapped_column(String(30), primary_key=True)
    menu_meal_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_meal_types.id", ondelete="RESTRICT"), nullable=False,
    )


class PostpartumReplacementGroup(AuditColumns, Base):
    __tablename__ = "postpartum_replacement_groups"
    __table_args__ = (
        CheckConstraint(meal_check("postpartum_meal"), name="ck_postpartum_replacement_groups_meal"),
        UniqueConstraint("id", "target_date", "postpartum_meal", name="uq_postpartum_replacement_groups_identity_slot"),
        Index("ix_postpartum_replacement_groups_target", "target_date", "postpartum_meal", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    postpartum_meal: Mapped[str] = mapped_column(String(30), nullable=False)
    replacement_dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    note: Mapped[str | None] = mapped_column(Text)


class PostpartumConflictHandling(AuditColumns, Base):
    __tablename__ = "postpartum_conflict_handlings"
    __table_args__ = (
        CheckConstraint(meal_check("postpartum_meal"), name="ck_postpartum_conflict_handlings_meal"),
        ForeignKeyConstraint(
            ["replacement_group_id", "target_date", "postpartum_meal"],
            [
                "postpartum_replacement_groups.id",
                "postpartum_replacement_groups.target_date",
                "postpartum_replacement_groups.postpartum_meal",
            ],
            ondelete="CASCADE",
            name="fk_postpartum_conflict_handlings_group_slot",
        ),
        UniqueConstraint("case_id", "original_menu_dish_id", name="uq_postpartum_conflict_handlings_item"),
        Index("ix_postpartum_conflict_handlings_target", "target_date", "postpartum_meal", "id"),
        Index("ix_postpartum_conflict_handlings_group_id", "replacement_group_id"),
        Index("ix_postpartum_conflict_handlings_original_menu_dish_id", "original_menu_dish_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    postpartum_meal: Mapped[str] = mapped_column(String(30), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postpartum_cases.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    # Deliberately not an FK: deleting/changing the ERP MenuDish must leave an identity that can be marked stale.
    original_menu_dish_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    original_dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    replacement_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
