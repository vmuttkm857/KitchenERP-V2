import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.schemas import PaginationMeta


class SupplierCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class SupplierUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class SupplierPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    contact_person: str | None
    phone: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class SupplierList(BaseModel):
    items: list[SupplierPublic]
    pagination: PaginationMeta
