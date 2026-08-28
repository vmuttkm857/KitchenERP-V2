from decimal import Decimal
from app.shared.domain.quantities import calculate_required_quantity,preparation_display

def test_known_formula_uses_decimal():
    assert calculate_required_quantity(Decimal("150"),100,Decimal("10"))==Decimal("16500.0")

def test_v1_human_display_is_safe_and_does_not_change_source():
    source=Decimal("16500")
    assert preparation_display(source,"g",True)==(Decimal("16.5"),"kg")
    assert source==Decimal("16500")
    assert preparation_display(Decimal("2500"),"ml",True)==(Decimal("2.5"),"L")
    assert preparation_display(Decimal("83.333333"),"g",False)==(Decimal("83.33"),"g")
    assert preparation_display(Decimal("2"),"斤",True)==(Decimal("2"),"斤")
