import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class DishProductionProfile(AuditColumns, Base):
    __tablename__ = "dish_production_profiles"
    __table_args__ = (CheckConstraint("max_batch_size > 0", name="ck_dish_production_profiles_max_batch_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    max_batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    image_filename: Mapped[str | None] = mapped_column(String(80))
    image_mime_type: Mapped[str | None] = mapped_column(String(40))
    image_size_bytes: Mapped[int | None] = mapped_column(Integer)


class ProductionBatchVersion(AuditColumns, Base):
    __tablename__ = "production_batch_versions"
    __table_args__ = (
        CheckConstraint("serving_count > 0", name="ck_production_batch_versions_servings_positive"),
        UniqueConstraint("profile_id", "serving_count", name="uq_production_batch_versions_profile_servings"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dish_production_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    serving_count: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(150))
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text)


USAGE_CATEGORIES = ("main_ingredient", "preprocessing", "marinade", "seasoning", "sauce", "final_addition", "garnish")


class ProductionBatchIngredient(AuditColumns, Base):
    __tablename__ = "production_batch_ingredients"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_production_batch_ingredients_quantity_nonnegative"),
        CheckConstraint("sort_order >= 0", name="ck_production_batch_ingredients_sort_nonnegative"),
        CheckConstraint("usage_category IN ('main_ingredient','preprocessing','marinade','seasoning','sauce','final_addition','garnish')", name="ck_production_batch_ingredients_usage"),
        UniqueConstraint("version_id", "ingredient_id", name="uq_production_batch_ingredients_version_ingredient"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("production_batch_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    dish_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("dish_ingredients.id", ondelete="SET NULL"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    usage_category: Mapped[str] = mapped_column(String(32), nullable=False, default="main_ingredient", server_default="main_ingredient")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    quantity_note: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(1000))


STEP_TYPES = ("wash", "cut", "chop", "marinate", "blanch", "thaw", "stir_fry", "boil", "braise", "steam", "bake", "fry", "pan_fry", "add_ingredient", "add_water", "stir", "flip", "thicken", "sauce", "garnish", "final_addition", "portion", "plating", "quality_check", "other")


class ProductionProcessStep(AuditColumns, Base):
    __tablename__ = "production_process_steps"
    __table_args__ = (
        CheckConstraint("step_order >= 1", name="ck_production_process_steps_order_positive"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_production_process_steps_duration_nonnegative"),
        CheckConstraint("temperature_celsius IS NULL OR (temperature_celsius >= -100 AND temperature_celsius <= 500)", name="ck_production_process_steps_temperature_range"),
        CheckConstraint("batch_size IS NULL OR batch_size > 0", name="ck_production_process_steps_batch_positive"),
        CheckConstraint("servings_per_tray IS NULL OR servings_per_tray > 0", name="ck_production_process_steps_tray_positive"),
        CheckConstraint("trays_per_batch IS NULL OR trays_per_batch > 0", name="ck_production_process_steps_trays_positive"),
        CheckConstraint("step_type IN ('wash','cut','chop','marinate','blanch','thaw','stir_fry','boil','braise','steam','bake','fry','pan_fry','add_ingredient','add_water','stir','flip','thicken','sauce','garnish','final_addition','portion','plating','quality_check','other')", name="ck_production_process_steps_type"),
        UniqueConstraint("version_id", "step_order", name="uq_production_process_steps_version_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("production_batch_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(150))
    instruction: Mapped[str | None] = mapped_column(Text)
    equipment: Mapped[str | None] = mapped_column(String(150))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    temperature_celsius: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    batch_size: Mapped[int | None] = mapped_column(Integer)
    servings_per_tray: Mapped[int | None] = mapped_column(Integer)
    trays_per_batch: Mapped[int | None] = mapped_column(Integer)
    quantity_note: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(1000))
