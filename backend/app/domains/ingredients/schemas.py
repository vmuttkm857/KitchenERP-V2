import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.shared.schemas import PaginationMeta


class IngredientCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    category_id: uuid.UUID
    unit: str = Field(min_length=1, max_length=30)
    current_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    primary_supplier_id: uuid.UUID | None = None
    purchase_unit: str | None = Field(default=None, max_length=30)
    package_size: Decimal = Field(default=Decimal("1"), ge=0, max_digits=18, decimal_places=6)
    minimum_order_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    notes: str | None = Field(default=None, max_length=1000)
    price_effective_date: date = Field(default_factory=date.today)
    price_notes: str | None = Field(default=None, max_length=1000)


class IngredientUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    category_id: uuid.UUID | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    current_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    primary_supplier_id: uuid.UUID | None = None
    purchase_unit: str | None = Field(default=None, max_length=30)
    package_size: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    minimum_order_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    notes: str | None = Field(default=None, max_length=1000)
    price_effective_date: date | None = None
    price_notes: str | None = Field(default=None, max_length=1000)


class IngredientPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    category_id: uuid.UUID
    category_name: str
    unit: str
    current_price: Decimal
    primary_supplier_id: uuid.UUID | None
    supplier_name: str | None
    purchase_unit: str | None
    package_size: Decimal
    minimum_order_quantity: Decimal
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID

    @field_serializer("current_price", "package_size", "minimum_order_quantity")
    def serialize_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class IngredientList(BaseModel):
    items: list[IngredientPublic]
    pagination: PaginationMeta


class PriceHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ingredient_id: uuid.UUID
    supplier_id: uuid.UUID | None
    price: Decimal
    unit: str
    effective_date: date
    notes: str | None
    created_at: datetime
    created_by: uuid.UUID

    @field_serializer("price")
    def serialize_price(self, value: Decimal) -> str:
        return format(value, "f")
