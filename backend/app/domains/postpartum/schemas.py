import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.schemas import PaginationMeta


DeliveryType = Literal["vaginal", "cesarean"]
Meal = Literal["breakfast", "lunch", "dinner"]
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


class CaseList(BaseModel):
    items: list[CasePublic]
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
