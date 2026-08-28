from dataclasses import dataclass
from decimal import Decimal


_UNIT_ALIASES = {"l": "L", "ml": "ml", "g": "g", "kg": "kg", "斤": "斤"}
_WEIGHT_IN_GRAMS = {"g": Decimal("1"), "kg": Decimal("1000"), "斤": Decimal("600")}
_VOLUME_IN_ML = {"ml": Decimal("1"), "L": Decimal("1000")}


@dataclass(frozen=True)
class ConversionResult:
    quantity: Decimal | None
    convertible: bool


def normalize_unit(unit: str) -> str:
    stripped = unit.strip()
    if stripped == "mL":
        return stripped
    return _UNIT_ALIASES.get(stripped.lower(), stripped)


def convert_quantity(quantity: Decimal, source_unit: str, target_unit: str) -> ConversionResult:
    source = normalize_unit(source_unit)
    target = normalize_unit(target_unit)
    if source == target:
        return ConversionResult(quantity, True)
    for dimension in (_WEIGHT_IN_GRAMS, _VOLUME_IN_ML):
        if source in dimension and target in dimension:
            base_quantity = quantity * dimension[source]
            return ConversionResult(base_quantity / dimension[target], True)
    return ConversionResult(None, False)


def calculate_recipe_cost(
    quantity: Decimal,
    loss_rate: Decimal,
    recipe_unit: str,
    ingredient_unit: str,
    current_price: Decimal,
) -> Decimal | None:
    with_loss = quantity * (Decimal("1") + loss_rate / Decimal("100"))
    converted = convert_quantity(with_loss, recipe_unit, ingredient_unit)
    if not converted.convertible or converted.quantity is None:
        return None
    return converted.quantity * current_price
