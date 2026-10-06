import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.domains.order_adjustments.reuse import build_reuse_preview
from app.domains.order_adjustments.schemas import OrderingAdjustmentMenuPair


PREVIOUS_MENU=uuid.uuid4();CURRENT_MENU=uuid.uuid4();INGREDIENT=uuid.uuid4();SUPPLIER=uuid.uuid4()
MENUS_PREVIOUS=[{"menu_id":str(PREVIOUS_MENU),"start_date":"2026-09-28"}]
MENUS_CURRENT=[{"menu_id":str(CURRENT_MENU),"start_date":"2026-10-05"}]
PAIR=[OrderingAdjustmentMenuPair(previous_menu_id=PREVIOUS_MENU,current_menu_id=CURRENT_MENU)]


def line(menu,day,meal,dish,recipe,system="1.710000",adjusted=None,sort=1,ingredient=INGREDIENT,supplier=SUPPLIER,unit="kg"):
    return SimpleNamespace(
        id=uuid.uuid4(),source_menu_id=menu,requirement_date=date.fromisoformat(day),meal_type_name_snapshot=meal,
        source_dish_id=dish,source_dish_ingredient_id=recipe,source_ingredient_id=ingredient,source_supplier_id=supplier,
        system_quantity=Decimal(system),adjusted_quantity=None if adjusted is None else Decimal(adjusted),system_unit=unit,
        menu_dish_sort_order_snapshot=sort,dish_name_snapshot=f"dish-{dish}",ingredient_name_snapshot="ingredient",
    )


def statuses(previous,current):
    return {item["current_line_id"]:item for item in build_reuse_preview(previous,current,MENUS_PREVIOUS,MENUS_CURRENT,PAIR)}


def test_partial_replacement_insert_delete_and_reorder_do_not_block_unchanged_lines():
    dishes=[uuid.uuid4() for _ in range(5)];recipes=[uuid.uuid4() for _ in range(5)]
    previous=[line(PREVIOUS_MENU,"2026-09-28","午餐",dishes[i],recipes[i],adjusted=str(i+2),sort=i+1) for i in range(4)]
    # C is replaced by X; A/B/D remain, with D changing sort order.
    current=[line(CURRENT_MENU,"2026-10-05","午餐",dishes[0],recipes[0],sort=3),line(CURRENT_MENU,"2026-10-05","午餐",dishes[1],recipes[1],sort=1),line(CURRENT_MENU,"2026-10-05","午餐",dishes[4],recipes[4],sort=2),line(CURRENT_MENU,"2026-10-05","午餐",dishes[3],recipes[3],sort=4)]
    result=statuses(previous,current)
    assert [result[value.id]["status"] for value in current]==["safe_to_reuse","safe_to_reuse","no_match","safe_to_reuse"]

    # Insert NEW before B/C and reorder all unchanged dishes; sort order is presentation metadata only.
    inserted=[line(CURRENT_MENU,"2026-10-05","午餐",dishes[0],recipes[0],sort=1),line(CURRENT_MENU,"2026-10-05","午餐",dishes[4],recipes[4],sort=2),line(CURRENT_MENU,"2026-10-05","午餐",dishes[1],recipes[1],sort=3),line(CURRENT_MENU,"2026-10-05","午餐",dishes[2],recipes[2],sort=4)]
    result=statuses(previous,inserted)
    assert [result[value.id]["status"] for value in inserted]==["safe_to_reuse","no_match","safe_to_reuse","safe_to_reuse"]

    # Delete B and reorder C/A: remaining occurrences continue to match independently.
    deleted=[line(CURRENT_MENU,"2026-10-05","午餐",dishes[2],recipes[2],sort=1),line(CURRENT_MENU,"2026-10-05","午餐",dishes[0],recipes[0],sort=2)]
    assert all(item["status"]=="safe_to_reuse" for item in statuses(previous,deleted).values())


def test_changed_context_quantity_recipe_and_manual_values_are_classified_safely():
    dish=uuid.uuid4();recipe=uuid.uuid4();previous=[line(PREVIOUS_MENU,"2026-09-28","午餐",dish,recipe,adjusted="0")]
    same=line(CURRENT_MENU,"2026-10-05","午餐",dish,recipe)
    assert statuses(previous,[same])[same.id]["status"]=="safe_to_reuse"
    assert statuses(previous,[same])[same.id]["reused_quantity"]==Decimal("0.000000")

    changed_quantity=line(CURRENT_MENU,"2026-10-05","午餐",dish,recipe,system="2.35")
    assert statuses(previous,[changed_quantity])[changed_quantity.id]["status"]=="reference_only"
    already_adjusted=line(CURRENT_MENU,"2026-10-05","午餐",dish,recipe,adjusted="3")
    assert statuses(previous,[already_adjusted])[already_adjusted.id]["reason_codes"]==["CURRENT_ALREADY_ADJUSTED"]
    changed_recipe=line(CURRENT_MENU,"2026-10-05","午餐",dish,uuid.uuid4())
    assert statuses(previous,[changed_recipe])[changed_recipe.id]["status"]=="no_match"
    new_dish_same_ingredient=line(CURRENT_MENU,"2026-10-05","午餐",uuid.uuid4(),recipe)
    assert statuses(previous,[new_dish_same_ingredient])[new_dish_same_ingredient.id]["status"]=="no_match"
    moved_day=line(CURRENT_MENU,"2026-10-06","午餐",dish,recipe)
    moved_meal=line(CURRENT_MENU,"2026-10-05","晚餐",dish,recipe)
    assert statuses(previous,[moved_day])[moved_day.id]["status"]=="no_match"
    assert statuses(previous,[moved_meal])[moved_meal.id]["status"]=="no_match"


def test_units_are_converted_with_decimal_precision_and_ambiguous_matches_never_apply():
    dish=uuid.uuid4();recipe=uuid.uuid4()
    previous=[line(PREVIOUS_MENU,"2026-09-28","午餐",dish,recipe,system="1710",adjusted="2000",unit="g")]
    current=line(CURRENT_MENU,"2026-10-05","午餐",dish,recipe,system="1.71",unit="kg")
    result=statuses(previous,[current])[current.id]
    assert result["status"]=="safe_to_reuse" and result["reused_quantity"]==Decimal("2.000000")
    precise=line(CURRENT_MENU,"2026-10-05","午餐",dish,recipe,system="1.710001",unit="kg")
    assert statuses(previous,[precise])[precise.id]["status"]=="reference_only"
    duplicate=[previous[0],line(PREVIOUS_MENU,"2026-09-28","午餐",dish,recipe,adjusted="2")]
    assert statuses(duplicate,[current])[current.id]["status"]=="ambiguous"
