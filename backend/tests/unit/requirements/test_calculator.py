import uuid
from datetime import date
from decimal import Decimal

from app.domains.requirements.calculator import calculate_requirement_rows,supplier_groups


INGREDIENT_ID=uuid.uuid4();DISH_ID=uuid.uuid4();DETAIL_ID=uuid.uuid4();MENU_ID=uuid.uuid4();MEAL_ID=uuid.uuid4();SUPPLIER_ID=uuid.uuid4()


def source(**changes):
    row={"menu_id":MENU_ID,"menu_name":"手算菜單","menu_is_active":True,"menu_date":date(2026,9,1),"meal_type_id":MEAL_ID,"meal_type_name":"午餐","meal_type_is_active":True,"menu_dish_id":uuid.uuid4(),"diner_count":10,"dish_id":DISH_ID,"dish_code":"D1","dish_name":"雞肉料理","dish_is_active":True,"recipe_detail_id":DETAIL_ID,"recipe_quantity":Decimal("100"),"recipe_unit":"g","loss_rate":Decimal("10"),"ingredient_id":INGREDIENT_ID,"ingredient_code":"I1","ingredient_name":"雞肉","base_unit":"kg","current_price":Decimal("200"),"supplier_id":SUPPLIER_ID,"purchase_unit":"箱","package_size":Decimal("10"),"minimum_order_quantity":Decimal("5"),"ingredient_is_active":True,"supplier_name":"供應商A","supplier_is_active":True}
    row.update(changes);return row


def test_known_manual_decimal_answer_and_v1_purchase_initial_value():
    rows,anomalies=calculate_requirement_rows([source()]);row=rows[0]
    assert row["requirement_quantity"]==Decimal("1.1")
    assert row["suggested_purchase_quantity"]==Decimal("1.1")
    assert row["suggested_purchase_unit"]=="kg"
    assert row["estimated_cost"]==Decimal("220.0")
    assert row["package_size"]==Decimal("10") and row["minimum_order_quantity"]==Decimal("5")
    assert anomalies==[]


def test_shared_ingredient_aggregates_by_stable_id_and_final_unit():
    second=source(menu_id=uuid.uuid4(),menu_date=date(2026,9,2),recipe_detail_id=uuid.uuid4(),recipe_quantity=Decimal("0.2"),recipe_unit="kg",loss_rate=Decimal("0"),diner_count=5)
    rows,_=calculate_requirement_rows([source(),second]);assert len(rows)==1
    assert rows[0]["requirement_quantity"]==Decimal("2.1") and rows[0]["total_diner_count"]==15


def test_jin_and_volume_conversion_known_answers():
    jin=source(recipe_quantity=Decimal("0.5"),recipe_unit="斤",base_unit="kg",loss_rate=Decimal("0"),diner_count=2)
    water=source(ingredient_id=uuid.uuid4(),ingredient_code="W",ingredient_name="水",recipe_detail_id=uuid.uuid4(),recipe_quantity=Decimal("250"),recipe_unit="ml",base_unit="L",loss_rate=Decimal("0"),diner_count=4,current_price=Decimal("2"))
    rows,_=calculate_requirement_rows([jin,water]);by_code={row["ingredient_code"]:row for row in rows}
    assert by_code["I1"]["requirement_quantity"]==Decimal("0.6")
    assert by_code["W"]["requirement_quantity"]==Decimal("1") and by_code["W"]["estimated_cost"]==Decimal("2")


def test_incompatible_units_missing_supplier_and_missing_price_are_structured():
    bad=source(recipe_unit="個",supplier_id=None,supplier_name=None,current_price=None)
    rows,anomalies=calculate_requirement_rows([bad]);row=rows[0]
    assert row["requirement_quantity"]==Decimal("1100") and row["requirement_unit"]=="個"
    assert row["suggested_purchase_quantity"] is None and row["estimated_cost"] is None
    assert {item["code"] for item in anomalies}=={"INCOMPATIBLE_UNIT","MISSING_SUPPLIER"}
    priced_missing=source(current_price=None)
    _,price_anomalies=calculate_requirement_rows([priced_missing])
    assert "MISSING_PRICE" in {item["code"] for item in price_anomalies}


def test_missing_recipe_zero_quantity_and_supplier_grouping():
    missing=source(recipe_detail_id=None,ingredient_id=None)
    zero=source(recipe_detail_id=uuid.uuid4(),recipe_quantity=Decimal("0"))
    valid=source();rows,anomalies=calculate_requirement_rows([missing,zero,valid])
    assert len(rows)==1 and {item["code"] for item in anomalies}=={"MISSING_RECIPE","ZERO_RECIPE_QUANTITY"}
    groups=supplier_groups(rows);assert groups[0]["known_estimated_cost"]==Decimal("220.0")
