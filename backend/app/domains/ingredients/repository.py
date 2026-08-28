from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.categories.models import IngredientCategory
from app.domains.ingredients.models import Ingredient, IngredientPriceHistory
from app.domains.suppliers.models import Supplier


class IngredientRepository:
    def __init__(self, session: Session) -> None: self.session = session
    def add(self, ingredient: Ingredient) -> None: self.session.add(ingredient)
    def add_history(self, history: IngredientPriceHistory) -> None: self.session.add(history)
    def get_model(self, ingredient_id: uuid.UUID) -> Ingredient | None: return self.session.get(Ingredient, ingredient_id)
    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        statement = select(Ingredient.id).where(func.lower(Ingredient.code) == code.lower())
        if exclude_id: statement = statement.where(Ingredient.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None
    def category(self, category_id: uuid.UUID) -> IngredientCategory | None: return self.session.get(IngredientCategory, category_id)
    def supplier(self, supplier_id: uuid.UUID) -> Supplier | None: return self.session.get(Supplier, supplier_id)
    def _view_statement(self):
        return select(
            Ingredient.id, Ingredient.code, Ingredient.name, Ingredient.category_id,
            IngredientCategory.name.label("category_name"), Ingredient.unit,
            Ingredient.current_price, Ingredient.primary_supplier_id,
            Supplier.name.label("supplier_name"), Ingredient.purchase_unit,
            Ingredient.package_size, Ingredient.minimum_order_quantity, Ingredient.notes,
            Ingredient.is_active, Ingredient.created_at, Ingredient.updated_at,
            Ingredient.created_by, Ingredient.updated_by,
        ).join(IngredientCategory, IngredientCategory.id == Ingredient.category_id).outerjoin(Supplier, Supplier.id == Ingredient.primary_supplier_id)
    def get_view(self, ingredient_id: uuid.UUID):
        return self.session.execute(self._view_statement().where(Ingredient.id == ingredient_id)).mappings().one_or_none()
    def list(self, page: int, page_size: int, active: bool | None, search: str | None, category_id: uuid.UUID | None) -> tuple[list[dict], int]:
        filters = []
        if active is not None: filters.append(Ingredient.is_active == active)
        if category_id: filters.append(Ingredient.category_id == category_id)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(Ingredient.code).like(term), func.lower(Ingredient.name).like(term)))
        total = self.session.scalar(select(func.count()).select_from(Ingredient).where(*filters)) or 0
        statement = self._view_statement().where(*filters).order_by(func.lower(Ingredient.code), Ingredient.id).offset((page-1)*page_size).limit(page_size)
        return [dict(row) for row in self.session.execute(statement).mappings()], total
    def price_history(self, ingredient_id: uuid.UUID) -> list[IngredientPriceHistory]:
        statement = select(IngredientPriceHistory).where(IngredientPriceHistory.ingredient_id == ingredient_id).order_by(IngredientPriceHistory.effective_date.desc(), IngredientPriceHistory.created_at.desc())
        return list(self.session.scalars(statement))
    def has_history(self, ingredient_id: uuid.UUID) -> bool:
        return self.session.scalar(select(IngredientPriceHistory.id).where(IngredientPriceHistory.ingredient_id == ingredient_id).limit(1)) is not None
    def has_recipe_references(self, ingredient_id: uuid.UUID) -> bool:
        from app.domains.recipes.models import DishIngredient
        return self.session.scalar(select(DishIngredient.id).where(DishIngredient.ingredient_id == ingredient_id).limit(1)) is not None
    def delete(self, ingredient: Ingredient) -> None: self.session.delete(ingredient)
