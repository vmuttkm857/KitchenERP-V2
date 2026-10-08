import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.domains.requirements.schemas import RequirementCriteria
from app.shared.schemas import PaginationMeta


class OrderingAdjustmentCreate(BaseModel):
    criteria: RequirementCriteria
    notes: str | None = Field(default=None, max_length=2000)


class OrderingAdjustmentLineUpdate(BaseModel):
    id: uuid.UUID
    adjusted_quantity: Decimal | None = None
    adjusted_unit: str | None = None

    @field_validator("adjusted_quantity")
    @classmethod
    def valid_quantity(cls, value):
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError("adjusted_quantity must be a finite non-negative number")
        return value

    @model_validator(mode="after")
    def valid_pair(self):
        if self.adjusted_quantity is None and self.adjusted_unit is not None:
            raise ValueError("adjusted_unit requires adjusted_quantity")
        if (
            self.adjusted_quantity is not None
            and "adjusted_unit" in self.model_fields_set
            and self.adjusted_unit is None
        ):
            raise ValueError("adjusted_unit cannot be null when adjusted_quantity is provided")
        return self


class OrderingAdjustmentBatchUpdate(BaseModel):
    lock_version: int = Field(ge=1)
    lines: list[OrderingAdjustmentLineUpdate] = Field(min_length=1)

    @field_validator("lines")
    @classmethod
    def unique_lines(cls, value):
        if len({line.id for line in value}) != len(value): raise ValueError("line ids must be unique")
        return value


class OrderingAdjustmentAction(BaseModel):
    lock_version: int = Field(ge=1)


class OrderingAdjustmentUnitConversion(BaseModel):
    lock_version: int = Field(ge=1)
    conversion: Literal["g_and_jin_to_kg", "g_to_kg", "jin_to_g"]


class OrderingAdjustmentMenuPair(BaseModel):
    previous_menu_id: uuid.UUID
    current_menu_id: uuid.UUID


class OrderingAdjustmentReusePreviewRequest(BaseModel):
    previous_sheet_id: uuid.UUID
    current_lock_version: int = Field(ge=1)
    previous_lock_version: int = Field(ge=1)
    menu_pairs: list[OrderingAdjustmentMenuPair] = Field(min_length=1)

    @field_validator("menu_pairs")
    @classmethod
    def unique_menu_pairs(cls,value):
        if len({item.current_menu_id for item in value})!=len(value) or len({item.previous_menu_id for item in value})!=len(value):
            raise ValueError("menu pairs must be one-to-one")
        return value


class OrderingAdjustmentReuseApplyRequest(OrderingAdjustmentReusePreviewRequest):
    selected_current_line_ids: list[uuid.UUID] = Field(min_length=1)

    @field_validator("selected_current_line_ids")
    @classmethod
    def unique_selected_lines(cls,value):
        if len(set(value))!=len(value):raise ValueError("selected line ids must be unique")
        return value


class OrderingAdjustmentReuseLine(BaseModel):
    status:Literal["safe_to_reuse","reference_only","no_match","ambiguous"]
    reason_codes:list[str]
    current_line_id:uuid.UUID;previous_line_id:uuid.UUID|None;current_menu_id:uuid.UUID
    requirement_date:date;meal_name:str;dish_name:str;ingredient_name:str
    current_system_quantity:Decimal;current_system_unit:str;current_adjusted_quantity:Decimal|None;current_adjusted_unit:str|None
    previous_system_quantity:Decimal|None;previous_system_unit:str|None;previous_adjusted_quantity:Decimal|None;previous_adjusted_unit:str|None
    reused_quantity:Decimal|None;reused_unit:str|None

    @field_serializer("current_system_quantity","current_adjusted_quantity","previous_system_quantity","previous_adjusted_quantity","reused_quantity")
    def reuse_decimal_string(self,value):return None if value is None else format(value,"f")


class OrderingAdjustmentReusePreview(BaseModel):
    current_sheet_id:uuid.UUID;previous_sheet_id:uuid.UUID
    current_lock_version:int;previous_lock_version:int
    summary:dict[str,int]
    lines:list[OrderingAdjustmentReuseLine]


class OrderingAdjustmentLinePublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; snapshot_item_id:uuid.UUID; source_line_key:str
    source_menu_id:uuid.UUID; menu_name_snapshot:str; source_menu_day_id:uuid.UUID; requirement_date:date
    source_meal_type_id:uuid.UUID; meal_type_name_snapshot:str; source_menu_meal_type_column_id:uuid.UUID|None
    meal_type_sort_order_snapshot:int; menu_meal_type_column_sort_order_snapshot:int|None
    source_menu_dish_id:uuid.UUID; menu_dish_sort_order_snapshot:int; source_dish_id:uuid.UUID; dish_code_snapshot:str; dish_name_snapshot:str; diner_count_snapshot:int
    source_dish_ingredient_id:uuid.UUID; dish_ingredient_sort_order_snapshot:int; source_ingredient_id:uuid.UUID; ingredient_code_snapshot:str; ingredient_name_snapshot:str
    source_supplier_id:uuid.UUID|None; supplier_name_snapshot:str|None
    quantity_per_person_snapshot:Decimal; loss_rate_snapshot:Decimal; recipe_unit_snapshot:str
    system_quantity:Decimal; system_unit:str; adjusted_quantity:Decimal|None; adjusted_unit:str|None; effective_quantity:Decimal; effective_unit:str
    modified:bool; review_required:bool; stale:bool; stale_reasons:list[str]

    @field_serializer("quantity_per_person_snapshot","loss_rate_snapshot","system_quantity","adjusted_quantity","effective_quantity")
    def decimal_string(self,value): return None if value is None else format(value,"f")


class OrderingAdjustmentDetail(BaseModel):
    id:uuid.UUID; baseline_snapshot_id:uuid.UUID; status:Literal["draft","confirmed","cancelled"]
    source_fingerprint:str; revision:int; lock_version:int; notes:str|None
    last_reuse_source_sheet_id:uuid.UUID|None; reuse_applied_at:datetime|None; reuse_applied_by:uuid.UUID|None
    criteria:dict[str,Any]; source_menus:list[dict[str,Any]]
    stale:bool; warnings:list[dict[str,Any]]
    confirmed_at:datetime|None; confirmed_by:uuid.UUID|None; created_at:datetime; updated_at:datetime
    created_by:uuid.UUID; updated_by:uuid.UUID; lines:list[OrderingAdjustmentLinePublic]


class OrderingAdjustmentSummary(BaseModel):
    id:uuid.UUID; baseline_snapshot_id:uuid.UUID; status:str; revision:int; lock_version:int
    criteria:dict[str,Any]; source_menus:list[dict[str,Any]]; notes:str|None
    created_at:datetime; updated_at:datetime; created_by:uuid.UUID; created_by_name:str
    stale:bool|None=None


class OrderingAdjustmentList(BaseModel):
    items:list[OrderingAdjustmentSummary]
    pagination:PaginationMeta
