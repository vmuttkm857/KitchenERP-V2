from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.dishes.service import DishService
from app.domains.nutrition.calculator import (
    DishNutritionResult, NutrientDefinition, RecipeNutritionCalculator, RecipeNutritionInput,
    normalize_nutrition_unit,
)
from app.domains.nutrition.repository import NutritionRepository


class DishNutritionService:
    def __init__(self, session: Session) -> None:
        self.repository = NutritionRepository(session)
        self.dishes = DishService(session)
        self.calculator = RecipeNutritionCalculator()

    def get(self, dish_id: uuid.UUID) -> DishNutritionResult:
        self.dishes.get_model(dish_id)
        return self.bulk({dish_id})[dish_id]

    def bulk(self, dish_ids: set[uuid.UUID]) -> dict[uuid.UUID, DishNutritionResult]:
        return self.bulk_report(dish_ids)[1]

    def bulk_report(self, dish_ids: set[uuid.UUID]) -> tuple[tuple[NutrientDefinition, ...], dict[uuid.UUID, DishNutritionResult]]:
        if not dish_ids:
            return (), {}
        nutrient_models = self.repository.reportable_nutrients()
        nutrients = tuple(NutrientDefinition(item.code, item.name, item.unit or "") for item in nutrient_models)
        rows = self.repository.recipe_inputs(dish_ids)
        food_ids = {row["nutrition_food_id"] for row in rows if row["nutrition_food_id"] is not None}
        ingredient_ids = {row["ingredient_id"] for row in rows}
        conversions = {
            (item.ingredient_id, item.unit): item.grams_per_unit
            for item in self.repository.nutrition_unit_conversions(ingredient_ids)
        }
        values: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(dict)
        for row in self.repository.food_values(food_ids, {item.code for item in nutrients}):
            values[row["food_id"]][row["code"]] = row["value"]
        grouped: dict[uuid.UUID, list[RecipeNutritionInput]] = defaultdict(list)
        for row in rows:
            food_id = row["nutrition_food_id"]
            grouped[row["dish_id"]].append(RecipeNutritionInput(
                ingredient_id=row["ingredient_id"], ingredient_name=row["ingredient_name"],
                quantity=row["quantity"], unit=row["unit"], nutrition_food_id=food_id,
                values=values.get(food_id, {}),
                grams_per_unit=conversions.get((row["ingredient_id"], normalize_nutrition_unit(row["unit"]))),
            ))
        return nutrients, {
            dish_id: self.calculator.calculate(dish_id, grouped[dish_id], nutrients) for dish_id in dish_ids
        }
