from decimal import Decimal
from types import SimpleNamespace
from app.domains.purchases.calculator import purchase_cost,purchase_values

def test_purchase_cost_converts_weight_and_volume_exactly():
    assert purchase_cost(Decimal("2"),"斤","kg",Decimal("200"))==Decimal("240.0")
    assert purchase_cost(Decimal("1250"),"ml","L",Decimal("2"))==Decimal("2.50")
    assert purchase_cost(Decimal("1"),"個","kg",Decimal("20")) is None

def test_package_and_minimum_are_reference_only():
    item=SimpleNamespace(adjusted_quantity=Decimal("11"),purchase_unit_snapshot="kg",requirement_unit="kg",unit_price_snapshot=Decimal("3"),package_size_snapshot=Decimal("5"),minimum_order_quantity_snapshot=Decimal("20"))
    final,cost,warnings=purchase_values(item)
    assert final==Decimal("11") and cost==Decimal("33")
    assert {warning["code"] for warning in warnings}=={"PURCHASE_RULE_REFERENCE_ONLY"}
