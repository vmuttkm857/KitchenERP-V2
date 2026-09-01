import uuid
from decimal import Decimal

from app.domains.nutrition.calculator import NutrientDefinition, RecipeNutritionCalculator, RecipeNutritionInput, normalize_nutrition_unit


def ingredient(name: str, quantity: str, unit: str, values: dict[str, str], mapped: bool = True, grams_per_unit: str | None = None):
    return RecipeNutritionInput(
        ingredient_id=uuid.uuid4(), ingredient_name=name, quantity=Decimal(quantity), unit=unit,
        nutrition_food_id=uuid.uuid4() if mapped else None,
        values={code: Decimal(value) for code, value in values.items()},
        grams_per_unit=Decimal(grams_per_unit) if grams_per_unit is not None else None,
    )


def calculate(*items): return RecipeNutritionCalculator().calculate(uuid.uuid4(), list(items))


def test_case_a_single_ingredient_uses_corrected_energy_per_100_g():
    result = calculate(ingredient("雞肉", "150", "g", {"corrected_energy": "200", "energy": "999"}))
    assert result.calorie_complete is True
    assert result.calorie_value == Decimal("300")


def test_case_b_multiple_ingredients_sum_without_partial_values():
    result = calculate(
        ingredient("雞肉", "150", "g", {"corrected_energy": "200"}),
        ingredient("油", "10", "g", {"corrected_energy": "900"}),
    )
    assert result.calorie_value == Decimal("390")


def test_safe_weight_units_g_kg_and_catty_are_exact():
    result = calculate(
        ingredient("克", "100", "g", {"corrected_energy": "1"}),
        ingredient("公斤", "0.1", "kg", {"corrected_energy": "1"}),
        ingredient("半斤", "0.5", "斤", {"corrected_energy": "1"}),
    )
    assert result.calorie_value == Decimal("5")


def test_case_c_mapping_or_calorie_missing_makes_whole_calorie_unavailable():
    missing_mapping = calculate(
        ingredient("雞肉", "150", "g", {"corrected_energy": "200"}),
        ingredient("裹粉", "20", "g", {}, mapped=False),
    )
    missing_value = calculate(
        ingredient("雞肉", "150", "g", {"corrected_energy": "200"}),
        ingredient("裹粉", "20", "g", {"protein": "3"}),
    )
    assert missing_mapping.calorie_value is None
    assert missing_mapping.missing_calorie_ingredients[0].reason == "no_nutrition_mapping"
    assert missing_value.calorie_value is None
    assert missing_value.missing_calorie_ingredients[0].reason == "nutrient_missing"


def test_case_d_each_nutrient_has_independent_completeness():
    result = calculate(
        ingredient("雞肉", "150", "g", {"corrected_energy": "200", "protein": "20", "fat": "2"}),
        ingredient("裹粉", "20", "g", {"corrected_energy": "300", "fat": "4"}),
    )
    assert result.calorie_value == Decimal("360")
    assert result.nutrients["protein"].value is None
    assert result.nutrients["fat"].value == Decimal("3.8")
    assert result.nutrients["sodium"].value is None


def test_case_e_numeric_zero_is_complete_not_missing():
    result = calculate(ingredient("零熱量", "100", "g", {"corrected_energy": "0", "protein": "0"}))
    assert result.calorie_complete is True and result.calorie_value == Decimal("0")
    assert result.nutrients["protein"].complete is True and result.nutrients["protein"].value == Decimal("0")


def test_case_f_volume_and_count_units_are_never_guessed_as_grams():
    for unit in ("ml", "L", "個", "包", "片"):
        result = calculate(ingredient("不可換算", "1", unit, {"corrected_energy": "100"}))
        assert result.calorie_value is None
        assert result.missing_calorie_ingredients[0].reason == "unsafe_unit_conversion"


def test_explicit_count_and_volume_conversions_are_exact_decimals():
    one_leg = calculate(ingredient("雞腿", "1", "隻", {"corrected_energy": "200"}, grams_per_unit="180"))
    two_legs = calculate(ingredient("雞腿", "2", "隻", {"corrected_energy": "200"}, grams_per_unit="180"))
    one_piece = calculate(ingredient("豆腐", "1", "個", {"corrected_energy": "80"}, grams_per_unit="125.5"))
    sauce_ml = calculate(ingredient("醬汁", "20", "ml", {"corrected_energy": "100"}, grams_per_unit="1.15"))
    sauce_l = calculate(ingredient("醬汁", "1", "L", {"corrected_energy": "100"}, grams_per_unit="1150"))
    one_package = calculate(ingredient("包裝食材", "1", "包", {"corrected_energy": "100"}, grams_per_unit="1000"))
    assert one_leg.calorie_value == Decimal("360")
    assert two_legs.calorie_value == Decimal("720")
    assert one_piece.calorie_value == Decimal("100.4")
    assert sauce_ml.calorie_value == Decimal("23")
    assert sauce_l.calorie_value == Decimal("1150")
    assert one_package.calorie_value == Decimal("1000")


def test_native_weight_units_take_precedence_over_explicit_conversion():
    result = calculate(ingredient("原生重量", "1", "kg", {"corrected_energy": "100"}, grams_per_unit="2"))
    assert result.calorie_value == Decimal("1000")


def test_unit_normalization_trims_full_width_space_and_casefolds_unknown_ascii():
    assert normalize_nutrition_unit(" 隻　") == "隻"
    assert normalize_nutrition_unit("PCS") == "pcs"
    assert normalize_nutrition_unit("l") == "L"
    assert normalize_nutrition_unit("mL") == "ml"


def test_dynamic_nutrients_preserve_order_units_missing_and_zero():
    definitions = tuple(NutrientDefinition(f"n{index}", f"營養素 {index}", "mg") for index in range(25))
    values = {definition.code: str(index) for index, definition in enumerate(definitions)}
    values.pop("n17")
    result = RecipeNutritionCalculator().calculate(
        uuid.uuid4(), [ingredient("完整測試", "100", "g", values)], definitions,
    )
    assert list(result.nutrients) == [definition.code for definition in definitions]
    assert result.nutrients["n0"].complete and result.nutrients["n0"].value == Decimal("0")
    assert result.nutrients["n17"].value is None
    assert result.nutrients["n24"].unit == "mg"


def test_decimal_precision_and_no_waste_rate_adjustment():
    item = ingredient("精確食材", "33.333333", "g", {"corrected_energy": "43.3184000000"})
    result = calculate(item)
    assert result.calorie_value == Decimal("43.3184000000") * Decimal("33.333333") / Decimal("100")


def test_empty_recipe_is_unavailable_with_explicit_reason():
    result = calculate()
    assert result.calorie_value is None
    assert result.missing_calorie_ingredients[0].reason == "no_recipe"
