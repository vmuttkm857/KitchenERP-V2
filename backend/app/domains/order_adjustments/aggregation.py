from collections import defaultdict
from decimal import Decimal

from app.domains.order_adjustments.exceptions import OrderingAdjustmentInvariantError
from app.shared.domain.quantities import convert_quantity, quantize_quantity


def aggregate_effective_quantities(lines, items):
    """Aggregate saved source-line quantities exactly as confirmation persists them."""
    by_id = {item.id: item for item in items}
    totals = defaultdict(Decimal)
    for line in lines:
        item = by_id.get(line.snapshot_item_id)
        if item is None:
            raise OrderingAdjustmentInvariantError()
        target_unit = item.purchase_unit_snapshot or item.requirement_unit
        quantity = line.adjusted_quantity if line.adjusted_quantity is not None else line.system_quantity
        unit = line.adjusted_unit if line.adjusted_quantity is not None else line.system_unit
        converted = convert_quantity(quantity, unit, target_unit)
        if not converted.convertible or converted.quantity is None:
            raise OrderingAdjustmentInvariantError()
        totals[item.id] += converted.quantity
    if set(totals) != set(by_id):
        raise OrderingAdjustmentInvariantError()
    return {item_id: quantize_quantity(quantity) for item_id, quantity in totals.items()}
