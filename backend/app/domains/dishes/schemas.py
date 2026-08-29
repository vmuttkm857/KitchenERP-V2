import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.schemas import PaginationMeta


class DishCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class DishUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class DishPublic(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category_id: uuid.UUID | None
    category_name: str | None
    notes: str | None
    recipe_ingredient_count: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class DishList(BaseModel):
    items: list[DishPublic]
    pagination: PaginationMeta
