import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, model_validator


class RequirementCriteria(BaseModel):
    menu_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    selected_dates: list[date] | None = Field(default=None, max_length=366)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if len(set(self.menu_ids)) != len(self.menu_ids): raise ValueError("menu_ids must be unique")
        if self.selected_dates is not None and (self.start_date is not None or self.end_date is not None): raise ValueError("Use selected_dates or a date range, not both")
        if (self.start_date is None) != (self.end_date is None): raise ValueError("start_date and end_date must be provided together")
        if self.start_date and self.end_date and self.end_date < self.start_date: raise ValueError("end_date must not precede start_date")
        if self.selected_dates is not None: self.selected_dates=sorted(set(self.selected_dates))
        return self


class RequirementAnomaly(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    related_entity_id: uuid.UUID | None
    related_entity_name: str | None
    context: dict[str, Any]


class RequirementRow(BaseModel):
    row_key: str
    ingredient_id: uuid.UUID
    ingredient_code: str
    ingredient_name: str
    supplier_id: uuid.UUID | None
    supplier_name: str | None
    supplier_code: str | None = None
    base_unit: str
    requirement_quantity: Decimal
    requirement_unit: str
    suggested_purchase_quantity: Decimal | None
    suggested_purchase_unit: str | None
    configured_purchase_unit: str | None
    package_size: Decimal
    minimum_order_quantity: Decimal
    current_price: Decimal | None
    estimated_cost: Decimal | None
    needs_review: bool
    total_diner_count: int
    source_count: int
    schedules: list[dict[str, Any]] = []

    @field_serializer("requirement_quantity", "suggested_purchase_quantity", "package_size", "minimum_order_quantity", "current_price", "estimated_cost")
    def decimal_string(self, value: Decimal | None): return None if value is None else format(value,"f")


class SupplierGroup(BaseModel):
    supplier_id: uuid.UUID | None
    supplier_name: str
    row_keys: list[str]
    known_estimated_cost: Decimal
    estimated_cost: Decimal | None
    needs_review: bool

    @field_serializer("known_estimated_cost", "estimated_cost")
    def decimal_string(self,value:Decimal|None): return None if value is None else format(value,"f")


class RequirementSourceMenu(BaseModel):
    menu_id: uuid.UUID
    menu_name: str
    start_date: date
    end_date: date
    is_active: bool


class AnomalySummary(BaseModel):
    total: int
    errors: int
    warnings: int


class RequirementResult(BaseModel):
    criteria: RequirementCriteria
    source_menus: list[RequirementSourceMenu]
    rows: list[RequirementRow]
    supplier_groups: list[SupplierGroup]
    known_estimated_cost: Decimal
    total_estimated_cost: Decimal | None
    anomalies: list[RequirementAnomaly]
    anomaly_summary: AnomalySummary

    @field_serializer("known_estimated_cost", "total_estimated_cost")
    def decimal_string(self,value:Decimal|None): return None if value is None else format(value,"f")
