from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.domains.ingredients.models import Ingredient
from app.domains.nutrition.models import IngredientNutritionUnitConversion, NutritionFood, NutritionFoodValue, NutritionImportBatch, NutritionNutrient
from app.domains.recipes.models import DishIngredient


class NutritionRepository:
    def __init__(self, session: Session): self.session = session
    def food(self, food_id: uuid.UUID): return self.session.get(NutritionFood, food_id)
    def tfda_by_code(self): return {item.external_code: item for item in self.session.scalars(select(NutritionFood).where(NutritionFood.source == "tfda"))}
    def nutrients_by_code(self): return {item.code: item for item in self.session.scalars(select(NutritionNutrient))}
    def corrected_energy_id(self): return self.session.scalar(select(NutritionNutrient.id).where(NutritionNutrient.code == "corrected_energy"))
    def reportable_nutrients(self):
        return list(self.session.scalars(
            select(NutritionNutrient)
            .where(NutritionNutrient.enabled.is_(True), NutritionNutrient.basis == "per_100_g")
            .order_by(NutritionNutrient.sort_order, NutritionNutrient.id)
        ))
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
    def recipe_inputs(self, dish_ids: set[uuid.UUID]):
        if not dish_ids: return []
        return list(self.session.execute(select(
            DishIngredient.dish_id, Ingredient.id.label("ingredient_id"), Ingredient.name.label("ingredient_name"),
            Ingredient.nutrition_food_id, DishIngredient.quantity, DishIngredient.unit,
        ).join(Ingredient, Ingredient.id == DishIngredient.ingredient_id)
         .where(DishIngredient.dish_id.in_(dish_ids))
         .order_by(DishIngredient.dish_id, DishIngredient.sort_order, DishIngredient.id)).mappings())
    def food_values(self, food_ids: set[uuid.UUID], nutrient_codes: set[str]):
        if not food_ids: return []
        return list(self.session.execute(select(
            NutritionFoodValue.food_id, NutritionNutrient.code, NutritionFoodValue.value,
        ).join(NutritionNutrient, NutritionNutrient.id == NutritionFoodValue.nutrient_id)
         .where(NutritionFoodValue.food_id.in_(food_ids), NutritionNutrient.code.in_(nutrient_codes))).mappings())
    def nutrition_unit_conversions(self, ingredient_ids: set[uuid.UUID]):
        if not ingredient_ids: return []
        return list(self.session.scalars(
            select(IngredientNutritionUnitConversion)
            .where(IngredientNutritionUnitConversion.ingredient_id.in_(ingredient_ids))
            .order_by(IngredientNutritionUnitConversion.ingredient_id, IngredientNutritionUnitConversion.unit)
        ))
    def ingredient_nutrition_unit_conversions(self, ingredient_id: uuid.UUID):
        return list(self.session.scalars(
            select(IngredientNutritionUnitConversion)
            .where(IngredientNutritionUnitConversion.ingredient_id == ingredient_id)
            .order_by(IngredientNutritionUnitConversion.unit, IngredientNutritionUnitConversion.id)
        ))
    def nutrition_unit_conversion(self, conversion_id: uuid.UUID):
        return self.session.get(IngredientNutritionUnitConversion, conversion_id)
