from decimal import Decimal
from typing import Literal


WeightUnitMode = Literal["original", "kg"]


def requirement_quantity_presentation(quantity, unit: str | None,
                                      mode: WeightUnitMode = "original"):
    """Return a display-only quantity/unit pair without mutating source data."""
    if mode == "kg" and unit == "g" and quantity is not None:
        return Decimal(str(quantity)) / Decimal("1000"), "kg"
    return quantity, unit
