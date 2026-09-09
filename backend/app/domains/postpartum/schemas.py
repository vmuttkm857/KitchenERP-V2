import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.schemas import PaginationMeta
from app.domains.postpartum.meals import Meal


DeliveryType = Literal["vaginal", "cesarean"]
CaseStatus = Literal["pending", "active", "paused", "ended"]
PreparationMode = Literal["no_herbal", "herbal", "rice_wine_sesame", "no_rice_wine_sesame"]


def _required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class CaseCreate(BaseModel):
    case_number: str = Field(max_length=50)
    name: str = Field(max_length=150)
    current_room: str = Field(max_length=100)
    delivery_type: DeliveryType
    delivery_date: date
    service_start_date: date
    service_start_meal: Meal
    service_end_date: date | None = None
    service_end_meal: Meal | None = None
    status: CaseStatus = "pending"
    preparation_mode: PreparationMode
    service_note: str | None = Field(default=None, max_length=5000)

    _strip_required = field_validator("case_number", "name", "current_room")(_required)

    @model_validator(mode="after")
    def valid_service_range(self):
        if (self.service_end_date is None) != (self.service_end_meal is None):
            raise ValueError("service end date and meal must be provided together")
        return self


class CaseUpdate(BaseModel):
    case_number: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=150)
    delivery_type: DeliveryType | None = None
    delivery_date: date | None = None
    service_start_date: date | None = None
    service_start_meal: Meal | None = None
    service_end_date: date | None = None
    service_end_meal: Meal | None = None
    status: CaseStatus | None = None
    preparation_mode: PreparationMode | None = None
    service_note: str | None = Field(default=None, max_length=5000)

    _strip_required = field_validator("case_number", "name")(_required)


class CasePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_number: str
    name: str
    current_room: str
    delivery_type: DeliveryType
    delivery_date: date
    service_start_date: date
    service_start_meal: Meal
    service_end_date: date | None
    service_end_meal: Meal | None
    status: CaseStatus
    preparation_mode: PreparationMode
    service_note: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class CaseRestrictionGroupSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str
    is_active: bool


class CaseListItem(CasePublic):
    restriction_groups: list[CaseRestrictionGroupSummary] = Field(default_factory=list)


class CaseList(BaseModel):
    items: list[CaseListItem]
    pagination: PaginationMeta


class RoomChangeCreate(BaseModel):
    room: str = Field(max_length=100)
    effective_date: date
    effective_meal: Meal

    _strip_room = field_validator("room")(_required)


class RoomHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    room: str
    effective_date: date
    effective_meal: Meal
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class PauseCreate(BaseModel):
    start_date: date
    start_meal: Meal
    end_date: date
    end_meal: Meal
    note: str | None = Field(default=None, max_length=5000)


class PauseUpdate(BaseModel):
    start_date: date | None = None
    start_meal: Meal | None = None
    end_date: date | None = None
    end_meal: Meal | None = None
    note: str | None = Field(default=None, max_length=5000)


class PausePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    start_date: date
    start_meal: Meal
    end_date: date
    end_meal: Meal
    note: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class CaseDetail(BaseModel):
    case: CasePublic
    room_history: list[RoomHistoryPublic]
    pauses: list[PausePublic]
    restriction_groups: list[CaseRestrictionGroupSummary] = Field(default_factory=list)


class CaseRestrictionGroupsReplace(BaseModel):
    restriction_group_ids: list[uuid.UUID] = Field(default_factory=list)


class CaseRestrictionGroupsPublic(BaseModel):
    case_id: uuid.UUID
    restriction_groups: list[CaseRestrictionGroupSummary] = Field(default_factory=list)


class RestrictionGroupCreate(BaseModel):
    name: str = Field(max_length=150)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: str | None = Field(default=None, max_length=5000)

    _strip_name = field_validator("name")(_required)


class RestrictionGroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "color" in self.model_fields_set and self.color is None:
            raise ValueError("color must not be null")
        return self


class RestrictionGroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str
    notes: str | None
    is_active: bool
    ingredient_count: int = 0
    dish_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class RestrictionGroupList(BaseModel):
    items: list[RestrictionGroupPublic]
    pagination: PaginationMeta


class RestrictionTargetPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class RestrictionGroupDetail(BaseModel):
    group: RestrictionGroupPublic
    ingredients: list[RestrictionTargetPublic]
    dishes: list[RestrictionTargetPublic]


class RestrictionAssociationsReplace(BaseModel):
    ingredient_ids: list[uuid.UUID] = Field(default_factory=list)
    dish_ids: list[uuid.UUID] = Field(default_factory=list)
