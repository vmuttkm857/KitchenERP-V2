import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.domains.dishes.schemas import DishPublic


class RecipeItemInput(BaseModel):
    id: uuid.UUID | None = None
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    unit: str = Field(min_length=1, max_length=30)
    loss_rate: Decimal = Field(default=Decimal("0"), ge=0, max_digits=9, decimal_places=6)
    sort_order: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class RecipeReplace(BaseModel):
    items: list[RecipeItemInput] = Field(max_length=500)


class RecipeItemPublic(BaseModel):
    id: uuid.UUID
    dish_id: uuid.UUID
    ingredient_id: uuid.UUID
    ingredient_code: str
    ingredient_name: str
    ingredient_unit: str
    supplier_name: str | None
    quantity: Decimal
    unit: str
    loss_rate: Decimal
    sort_order: int
    notes: str | None
    item_cost: Decimal | None
    cost_needs_review: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID

    @field_serializer("quantity", "loss_rate", "item_cost")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")


class RecipeAggregate(BaseModel):
    dish: DishPublic
    items: list[RecipeItemPublic]
    total_cost: Decimal | None
    cost_needs_review: bool
    requirement_ready: bool

    @field_serializer("total_cost")
    def serialize_total(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")
