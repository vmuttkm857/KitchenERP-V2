from __future__ import annotations

import uuid
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from app.shared.domain.quantities import normalize_unit


COMMON_NUTRIENTS = (
    ("corrected_energy", "修正熱量", "kcal"),
    ("protein", "蛋白質", "g"),
    ("fat", "脂肪", "g"),
    ("carbohydrate", "碳水化合物", "g"),
    ("dietary_fiber", "膳食纖維", "g"),
    ("sodium", "鈉", "mg"),
    ("potassium", "鉀", "mg"),
    ("calcium", "鈣", "mg"),
)
WEIGHT_IN_GRAMS = {"g": Decimal("1"), "kg": Decimal("1000"), "斤": Decimal("600")}


@dataclass(frozen=True)
class NutrientDefinition:
    code: str
    name: str
    unit: str


@dataclass(frozen=True)
class RecipeNutritionInput:
    ingredient_id: uuid.UUID
    ingredient_name: str
    quantity: Decimal
    unit: str
    nutrition_food_id: uuid.UUID | None
    values: dict[str, Decimal]
    grams_per_unit: Decimal | None = None


@dataclass(frozen=True)
class MissingNutritionIngredient:
    ingredient_id: uuid.UUID | None
    ingredient_name: str
    reason: str
    unit: str | None = None


@dataclass(frozen=True)
class NutrientCalculation:
    code: str
    name: str
    unit: str
    value: Decimal | None
    complete: bool
    missing_ingredients: tuple[MissingNutritionIngredient, ...]


@dataclass(frozen=True)
class DishNutritionResult:
    dish_id: uuid.UUID
    basis: str
    nutrients: dict[str, NutrientCalculation]

    @property
    def calorie_complete(self) -> bool:
        return self.nutrients["corrected_energy"].complete

    @property
    def calorie_value(self) -> Decimal | None:
        return self.nutrients["corrected_energy"].value

    @property
    def missing_calorie_ingredients(self) -> tuple[MissingNutritionIngredient, ...]:
        return self.nutrients["corrected_energy"].missing_ingredients


def normalize_nutrition_unit(unit: str) -> str:
    """Normalize storage/matching without treating distinct kitchen units as synonyms."""
    text = unicodedata.normalize("NFKC", unit).strip()
    canonical = {"g": "g", "kg": "kg", "ml": "ml", "l": "L"}
    if text.casefold() in canonical:
        return canonical[text.casefold()]
    normalized = normalize_unit(text)
    if normalized not in {"g", "kg", "斤", "ml", "L"} and normalized.isascii():
        return normalized.casefold()
    return normalized


def _grams(quantity: Decimal, unit: str, grams_per_unit: Decimal | None = None) -> Decimal | None:
    factor = WEIGHT_IN_GRAMS.get(normalize_unit(unit))
    if factor is not None:
        return quantity * factor
    return None if grams_per_unit is None else quantity * grams_per_unit


class RecipeNutritionCalculator:
    """Calculate one-person recipe nutrition from per-100-g values, without loss adjustments."""

    def calculate(
        self, dish_id: uuid.UUID, ingredients: list[RecipeNutritionInput],
        nutrients: tuple[NutrientDefinition, ...] | list[NutrientDefinition] | None = None,
    ) -> DishNutritionResult:
        calculated: dict[str, NutrientCalculation] = {}
        definitions = nutrients or tuple(NutrientDefinition(*item) for item in COMMON_NUTRIENTS)
        for definition in definitions:
            code, name, unit = definition.code, definition.name, definition.unit
            total = Decimal("0")
            missing: list[MissingNutritionIngredient] = []
            if not ingredients:
                missing.append(MissingNutritionIngredient(None, "尚未建立配方", "no_recipe"))
            for ingredient in ingredients:
                if ingredient.nutrition_food_id is None:
                    missing.append(MissingNutritionIngredient(
                        ingredient.ingredient_id, ingredient.ingredient_name, "no_nutrition_mapping", ingredient.unit,
                    ))
                    continue
                grams = _grams(ingredient.quantity, ingredient.unit, ingredient.grams_per_unit)
                if grams is None:
                    missing.append(MissingNutritionIngredient(
                        ingredient.ingredient_id, ingredient.ingredient_name, "unsafe_unit_conversion", ingredient.unit,
                    ))
                    continue
                value = ingredient.values.get(code)
                if value is None:
                    missing.append(MissingNutritionIngredient(
                        ingredient.ingredient_id, ingredient.ingredient_name, "nutrient_missing", ingredient.unit,
                    ))
                    continue
                total += value * grams / Decimal("100")
            complete = not missing
            calculated[code] = NutrientCalculation(
                code=code, name=name, unit=unit, value=total if complete else None,
                complete=complete, missing_ingredients=tuple(missing),
            )
        return DishNutritionResult(dish_id=dish_id, basis="per_person_recipe", nutrients=calculated)
