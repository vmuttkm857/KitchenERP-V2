from decimal import Decimal

from app.shared.domain.quantities import calculate_recipe_cost, convert_quantity


def test_weight_and_volume_conversions_are_decimal_safe() -> None:
    assert convert_quantity(Decimal("1"), "斤", "g").quantity == Decimal("600")
    assert convert_quantity(Decimal("1250"), "g", "kg").quantity == Decimal("1.25")
    assert convert_quantity(Decimal("2500"), "ml", "L").quantity == Decimal("2.5")


def test_unknown_dimensions_are_not_guessed_and_legacy_ml_is_not_runtime_compatible() -> None:
    assert not convert_quantity(Decimal("1"), "個", "kg").convertible
    assert not convert_quantity(Decimal("1"), "mL", "ml").convertible


def test_recipe_cost_includes_percentage_loss() -> None:
    assert calculate_recipe_cost(
        Decimal("500"), Decimal("10"), "g", "kg", Decimal("120")
    ) == Decimal("66.00")
