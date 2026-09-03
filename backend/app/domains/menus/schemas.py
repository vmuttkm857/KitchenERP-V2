import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.schemas import PaginationMeta


class MenuCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    start_date: date
    end_date: date
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.end_date < self.start_date: raise ValueError("end_date must not precede start_date")
        return self


class MenuUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    start_date: date | None = None
    end_date: date | None = None
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MenuPublic(BaseModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    category_id: uuid.UUID | None
    category_name: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class MenuList(BaseModel):
    items: list[MenuPublic]
    pagination: PaginationMeta


class MealTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=1, ge=1)


class MealTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=1)


class MealTypeReorder(BaseModel):
    ordered_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class MealTypePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    menu_id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class MealTypeColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=1, ge=1)


class MealTypeColumnUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class MealTypeColumnReorder(BaseModel):
    ordered_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class MealTypeColumnPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    menu_meal_type_id: uuid.UUID
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class MenuDishInput(BaseModel):
    id: uuid.UUID | None = None
    dish_id: uuid.UUID
    diner_count: int = Field(default=1, ge=0)
    notes: str | None = Field(default=None, max_length=1000)
    sort_order: int = Field(default=1, ge=1)


class MenuSlotInput(BaseModel):
    menu_day_id: uuid.UUID | None = None
    menu_date: date
    menu_meal_type_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=1000)
    dishes: list[MenuDishInput] = Field(default_factory=list, max_length=200)


class MenuEditorSave(BaseModel):
    slots: list[MenuSlotInput] = Field(max_length=5000)


class MenuDishPublic(BaseModel):
    id: uuid.UUID
    dish_id: uuid.UUID
    dish_code: str
    dish_name: str
    dish_category_name: str | None
    diner_count: int
    notes: str | None
    sort_order: int
    created_by: uuid.UUID
    updated_by: uuid.UUID


class MenuSlotPublic(BaseModel):
    menu_day_id: uuid.UUID
    menu_date: date
    menu_meal_type_id: uuid.UUID
    notes: str | None
    dishes: list[MenuDishPublic]


class MenuEditorAggregate(BaseModel):
    menu: MenuPublic
    dates: list[date]
    meal_types: list[MealTypePublic]
    meal_type_columns: list[MealTypeColumnPublic]
    slots: list[MenuSlotPublic]


class CopyDayCommand(BaseModel):
    source_menu_id: uuid.UUID
    source_date: date
    destination_date: date
    mode: Literal["add", "replace"] = "add"
    confirm_replace: bool = False

    @model_validator(mode="after")
    def replacement_is_confirmed(self):
        if self.mode == "replace" and not self.confirm_replace: raise ValueError("replace mode requires explicit confirmation")
        return self


class CopyWeekCommand(BaseModel):
    source_menu_id: uuid.UUID
    mode: Literal["add", "replace"] = "add"
    confirm_replace: bool = False

    @model_validator(mode="after")
    def replacement_is_confirmed(self):
        if self.mode == "replace" and not self.confirm_replace: raise ValueError("replace mode requires explicit confirmation")
        return self
