import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.schemas import PaginationMeta


CategoryKind = Literal["ingredient", "dish", "menu"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0)


class CategoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class CategoryList(BaseModel):
    items: list[CategoryPublic]
    pagination: PaginationMeta
