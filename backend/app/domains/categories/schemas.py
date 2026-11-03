import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.schemas import PaginationMeta


CategoryKind = Literal["ingredient", "dish", "menu"]


class CategoryColorInput(BaseModel):
    background_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("background_color")
    @classmethod
    def normalize_color(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class CategoryCreate(CategoryColorInput):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)


class CategoryUpdate(CategoryColorInput):
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


class DishCategoryPublic(CategoryPublic):
    background_color: str | None


class CategoryList(BaseModel):
    items: list[DishCategoryPublic | CategoryPublic]
    pagination: PaginationMeta
