import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.shared.schemas import PaginationMeta


class NutrientValueInput(BaseModel):
    corrected_energy: Decimal | None = Field(default=None, ge=0)
    energy: Decimal | None = Field(default=None, ge=0)
    protein: Decimal | None = Field(default=None, ge=0)
    fat: Decimal | None = Field(default=None, ge=0)
    carbohydrate: Decimal | None = Field(default=None, ge=0)
    dietary_fiber: Decimal | None = Field(default=None, ge=0)
    sodium: Decimal | None = Field(default=None, ge=0)
    potassium: Decimal | None = Field(default=None, ge=0)
    calcium: Decimal | None = Field(default=None, ge=0)


class ManualFoodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    brand: str | None = Field(default=None, max_length=200)
    source_note: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    nutrients: NutrientValueInput = Field(default_factory=NutrientValueInput)


class ManualFoodUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    brand: str | None = Field(default=None, max_length=200)
    source_note: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    nutrients: NutrientValueInput | None = None


class FoodSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; source: str; external_code: str | None; name: str; category: str | None; brand: str | None
    corrected_energy: Decimal | None; is_active: bool; active_in_latest_import: bool; created_at: datetime; updated_at: datetime
    @field_serializer("corrected_energy")
    def decimal_text(self, value): return format(value, "f") if value is not None else None


class FoodList(BaseModel): items: list[FoodSummary]; pagination: PaginationMeta


class NutrientPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; code: str; name: str; unit: str | None; basis: str; sort_order: int; enabled: bool; original_source_name: str | None


class FoodValue(BaseModel):
    code: str; name: str; unit: str | None; basis: str; value: Decimal
    @field_serializer("value")
    def decimal_text(self, value): return format(value, "f")


class FoodDetail(BaseModel):
    id: uuid.UUID; source: str; external_code: str | None; name: str; category: str | None; description: str | None
    aliases: list[str] | None; waste_rate: Decimal | None; brand: str | None; source_note: str | None; notes: str | None
    is_active: bool; active_in_latest_import: bool; values: list[FoodValue]
    @field_serializer("waste_rate")
    def decimal_text(self, value): return format(value, "f") if value is not None else None


class ImportPreview(BaseModel):
    header_row: int; total_rows: int; inserted_count: int; updated_count: int; unchanged_count: int; missing_count: int; error_count: int; errors: list[dict]


class ImportBatchPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; source: str; version_label: str | None; original_filename: str; imported_at: datetime; imported_by: uuid.UUID
    total_rows: int; inserted_count: int; updated_count: int; unchanged_count: int; missing_count: int; error_count: int; status: str; header_row: int


class ImportList(BaseModel): items: list[ImportBatchPublic]; pagination: PaginationMeta


class IngredientNutritionUpdate(BaseModel): nutrition_food_id: uuid.UUID | None = None


class NutritionUnitConversionCreate(BaseModel):
    unit: str = Field(min_length=1, max_length=30)
    grams_per_unit: Decimal = Field(gt=0, max_digits=24, decimal_places=10, allow_inf_nan=False)

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        if not value.strip(): raise ValueError("unit must not be blank")
        return value


class NutritionUnitConversionUpdate(BaseModel):
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    grams_per_unit: Decimal | None = Field(
        default=None, gt=0, max_digits=24, decimal_places=10, allow_inf_nan=False,
    )

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip(): raise ValueError("unit must not be blank")
        return value


class NutritionUnitConversionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ingredient_id: uuid.UUID
    unit: str
    grams_per_unit: Decimal
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID

    @field_serializer("grams_per_unit")
    def serialize_grams(self, value: Decimal) -> str:
        return format(value, "f")


class DishNutritionBulkRequest(BaseModel):
    dish_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class MissingNutritionIngredientPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ingredient_id: uuid.UUID | None
    ingredient_name: str
    reason: str
    unit: str | None = None


class NutrientCalculationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    unit: str
    value: Decimal | None
    complete: bool
    missing_ingredients: list[MissingNutritionIngredientPublic]

    @field_serializer("value")
    def serialize_value(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")


class DishNutritionPublic(BaseModel):
    dish_id: uuid.UUID
    basis: str
    calorie_complete: bool
    calorie_value: Decimal | None
    missing_calorie_ingredients: list[MissingNutritionIngredientPublic]
    nutrients: dict[str, NutrientCalculationPublic]

    @field_serializer("calorie_value")
    def serialize_calorie(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")


class DishNutritionBulkPublic(BaseModel):
    items: list[DishNutritionPublic]
