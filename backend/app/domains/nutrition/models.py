import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NutritionImportBatch(Base):
    __tablename__ = "nutrition_import_batches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    version_label: Mapped[str | None] = mapped_column(String(150))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    header_row: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    imported_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NutritionNutrient(Base):
    __tablename__ = "nutrition_nutrients"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    basis: Mapped[str] = mapped_column(String(30), nullable=False, default="per_100_g", server_default="per_100_g")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    original_source_name: Mapped[str | None] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class NutritionFood(Base):
    __tablename__ = "nutrition_foods"
    __table_args__ = (
        UniqueConstraint("source", "external_code", name="uq_nutrition_foods_source_external_code"),
        CheckConstraint("source IN ('tfda', 'manual')", name="ck_nutrition_foods_source"),
        CheckConstraint("(source = 'tfda' AND external_code IS NOT NULL) OR source = 'manual'", name="ck_nutrition_foods_source_code"),
        Index("ix_nutrition_foods_source_active", "source", "is_active", "active_in_latest_import"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    external_code: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    category: Mapped[str | None] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(String(2000))
    aliases: Mapped[list[str] | None] = mapped_column(JSONB)
    waste_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    brand: Mapped[str | None] = mapped_column(String(200))
    source_note: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(String(2000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    active_in_latest_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    source_hash: Mapped[str | None] = mapped_column(String(64))
    last_import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("nutrition_import_batches.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class NutritionFoodValue(Base):
    __tablename__ = "nutrition_food_values"
    food_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nutrition_foods.id", ondelete="CASCADE"), primary_key=True)
    nutrient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nutrition_nutrients.id", ondelete="RESTRICT"), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class IngredientNutritionUnitConversion(Base):
    __tablename__ = "ingredient_nutrition_unit_conversions"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "unit", name="uq_ingredient_nutrition_unit_conversions_ingredient_unit"),
        CheckConstraint("grams_per_unit > 0", name="ck_ingredient_nutrition_unit_conversions_grams_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    grams_per_unit: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
