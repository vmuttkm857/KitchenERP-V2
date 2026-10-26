from decimal import Decimal

from app.shared.domain.quantities import calculate_recipe_cost, classify_erp_unit, convert_quantity, quantize_quantity


def test_weight_and_volume_conversions_are_decimal_safe() -> None:
    assert convert_quantity(Decimal("1"), "斤", "g").quantity == Decimal("600")
    assert convert_quantity(Decimal("1250"), "g", "kg").quantity == Decimal("1.25")
    assert convert_quantity(Decimal("2500"), "ml", "L").quantity == Decimal("2.5")


def test_unknown_dimensions_are_not_guessed_and_legacy_ml_is_not_runtime_compatible() -> None:
    assert not convert_quantity(Decimal("1"), "個", "kg").convertible
    assert not convert_quantity(Decimal("1"), "mL", "ml").convertible


def test_erp_unit_classification_distinguishes_weight_non_weight_and_invalid_data() -> None:
    for unit in ("g", "kg", "斤", "KG"):
        assert classify_erp_unit(unit) == "weight"
    for unit in ("片", "個", "隻", "包", "盒", "袋", "箱", "ml", "L", "罐", "桶"):
        assert classify_erp_unit(unit) == "non_weight"
    for unit in (None, "", "   ", "公克", 123):
        assert classify_erp_unit(unit) == "invalid"


def test_recipe_cost_includes_percentage_loss() -> None:
    assert calculate_recipe_cost(
        Decimal("500"), Decimal("10"), "g", "kg", Decimal("120")
    ) == Decimal("66.00")


def test_persisted_quantity_rounding_is_explicit_half_up() -> None:
    assert quantize_quantity(Decimal("1.0000004")) == Decimal("1.000000")
    assert quantize_quantity(Decimal("1.0000005")) == Decimal("1.000001")
    assert quantize_quantity(Decimal("2.3456785")) == Decimal("2.345679")
