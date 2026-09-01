from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.domains.ingredients.models import Ingredient
from app.domains.nutrition.models import NutritionFood, NutritionFoodValue, NutritionImportBatch, NutritionNutrient


class NutritionRepository:
    def __init__(self, session: Session): self.session = session
    def food(self, food_id: uuid.UUID): return self.session.get(NutritionFood, food_id)
    def tfda_by_code(self): return {item.external_code: item for item in self.session.scalars(select(NutritionFood).where(NutritionFood.source == "tfda"))}
    def nutrients_by_code(self): return {item.code: item for item in self.session.scalars(select(NutritionNutrient))}
    def corrected_energy_id(self): return self.session.scalar(select(NutritionNutrient.id).where(NutritionNutrient.code == "corrected_energy"))
    def list_foods(self, *, source: str | None, page: int, page_size: int, search: str | None, category: str | None, active: bool | None):
        corrected = self.corrected_energy_id()
        energy = select(NutritionFoodValue.value).where(NutritionFoodValue.food_id == NutritionFood.id, NutritionFoodValue.nutrient_id == corrected).scalar_subquery() if corrected else None
        columns = [NutritionFood.id, NutritionFood.source, NutritionFood.external_code, NutritionFood.name, NutritionFood.category, NutritionFood.brand, NutritionFood.is_active, NutritionFood.active_in_latest_import, NutritionFood.created_at, NutritionFood.updated_at]
        columns.append(energy.label("corrected_energy") if energy is not None else func.cast(None, NutritionFoodValue.value.type).label("corrected_energy"))
        filters = []
        if source: filters.append(NutritionFood.source == source)
        if active is not None: filters.append(NutritionFood.is_active == active)
        if category: filters.append(NutritionFood.category == category)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(NutritionFood.name).like(term), func.lower(func.coalesce(NutritionFood.external_code, "")).like(term), func.lower(func.coalesce(NutritionFood.category, "")).like(term), func.lower(func.cast(NutritionFood.aliases, NutritionFood.name.type)).like(term)))
        total = self.session.scalar(select(func.count()).select_from(NutritionFood).where(*filters)) or 0
        statement = select(*columns).where(*filters).order_by(func.lower(NutritionFood.name), NutritionFood.id).offset((page-1)*page_size).limit(page_size)
        return [dict(row) for row in self.session.execute(statement).mappings()], total
    def detail(self, food_id: uuid.UUID):
        food = self.food(food_id)
        if not food: return None
        values = self.session.execute(select(NutritionNutrient.code, NutritionNutrient.name, NutritionNutrient.unit, NutritionNutrient.basis, NutritionFoodValue.value).join(NutritionFoodValue, NutritionFoodValue.nutrient_id == NutritionNutrient.id).where(NutritionFoodValue.food_id == food_id).order_by(NutritionNutrient.sort_order)).mappings()
        return food, [dict(row) for row in values]
    def categories(self, source: str): return list(self.session.scalars(select(NutritionFood.category).where(NutritionFood.source == source, NutritionFood.category.is_not(None)).distinct().order_by(NutritionFood.category)))
    def imports(self, page: int, page_size: int):
        total = self.session.scalar(select(func.count()).select_from(NutritionImportBatch)) or 0
        items = list(self.session.scalars(select(NutritionImportBatch).order_by(NutritionImportBatch.imported_at.desc()).offset((page-1)*page_size).limit(page_size)))
        return items, total
    def ingredient_uses(self, food_id: uuid.UUID): return self.session.scalar(select(Ingredient.id).where(Ingredient.nutrition_food_id == food_id).limit(1)) is not None
