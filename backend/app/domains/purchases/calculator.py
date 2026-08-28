from decimal import Decimal
from app.shared.domain.quantities import convert_quantity

def purchase_cost(quantity,purchase_unit,price_base_unit,unit_price):
    if unit_price is None:return None
    converted=convert_quantity(quantity,purchase_unit,price_base_unit)
    if not converted.convertible or converted.quantity is None:return None
    return converted.quantity*unit_price

def purchase_values(item):
    # V1 documents no package ceiling or minimum-order formula. Keep the
    # operator-confirmed physical quantity and retain both fields as references.
    final=item.adjusted_quantity
    cost=purchase_cost(final,item.purchase_unit_snapshot,item.requirement_unit,item.unit_price_snapshot)
    warnings=[]
    if item.package_size_snapshot!=Decimal("1") or item.minimum_order_quantity_snapshot>0:
        warnings.append({"code":"PURCHASE_RULE_REFERENCE_ONLY","severity":"warning","message":"Package size and minimum order are references; no automatic rounding was applied"})
    if cost is None: warnings.append({"code":"UNKNOWN_PURCHASE_COST","severity":"warning","message":"Purchase cost cannot be safely calculated"})
    return final,cost,warnings
