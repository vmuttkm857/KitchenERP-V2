from collections import OrderedDict
from datetime import date, timedelta

from app.domains.requirements.schemas import RequirementCriteria


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _included_dates(criteria, menu):
    menu_start, menu_end = _date(menu["start_date"]), _date(menu["end_date"])
    if criteria.selected_dates is not None:
        return sorted(value for value in criteria.selected_dates if menu_start <= value <= menu_end)
    start = max(criteria.start_date or menu_start, menu_start)
    end = min(criteria.end_date or menu_end, menu_end)
    dates = []
    while start <= end:
        dates.append(start)
        start += timedelta(days=1)
    return dates


def build_adjusted_weekly_result(snapshot, lines, menu_id, layout):
    """Build the existing weekly-kitchen renderer contract from saved adjustment lines."""
    menu = next(item for item in snapshot.source_menus if str(item["menu_id"]) == str(menu_id))
    criteria = RequirementCriteria.model_validate(snapshot.criteria)
    dates = _included_dates(criteria, menu)
    selected = [line for line in lines if line.source_menu_id == menu_id and line.requirement_date in dates]

    meals = OrderedDict()
    for meal in sorted(layout["meal_types"], key=lambda item: (item.sort_order, str(item.id))):
        meals[meal.id] = {"meal_type_id": meal.id, "meal_type_name": meal.name, "sort_order": meal.sort_order}
    for line in selected:
        meals.setdefault(line.source_meal_type_id, {
            "meal_type_id": line.source_meal_type_id,
            "meal_type_name": line.meal_type_name_snapshot,
            "sort_order": line.meal_type_sort_order_snapshot,
        })
    ordered_meals = sorted(meals.values(), key=lambda item: (item["sort_order"], str(item["meal_type_id"])))

    grouped = OrderedDict()
    for line in selected:
        key = (line.requirement_date, line.source_meal_type_id, line.source_menu_dish_id)
        dish = grouped.setdefault(key, {
            "dish_id": line.source_dish_id,
            "menu_dish_id": line.source_menu_dish_id,
            "menu_meal_type_column_id": line.source_menu_meal_type_column_id,
            "dish_code": line.dish_code_snapshot,
            "dish_name": line.dish_name_snapshot,
            "diner_count": line.diner_count_snapshot,
            "notes": None,
            "sort_order": line.menu_dish_sort_order_snapshot,
            "recipe_ready": True,
            "ingredients": [],
            "anomalies": [],
        })
        quantity = line.adjusted_quantity if line.adjusted_quantity is not None else line.system_quantity
        unit = line.adjusted_unit if line.adjusted_quantity is not None else line.system_unit
        dish["ingredients"].append({
            "ingredient_id": line.source_ingredient_id,
            "ingredient_code": line.ingredient_code_snapshot,
            "ingredient_name": line.ingredient_name_snapshot,
            "supplier_id": line.source_supplier_id,
            "supplier_name": line.supplier_name_snapshot,
            "required_quantity": quantity,
            "required_unit": unit,
            "display_quantity": quantity,
            "display_unit": unit,
            "sort_order": line.dish_ingredient_sort_order_snapshot,
            "anomalies": [],
        })

    for dish in grouped.values():
        dish["ingredients"].sort(key=lambda item: (item["sort_order"], str(item["ingredient_id"])))
    days = []
    for menu_date in dates:
        day_meals = []
        for meal in ordered_meals:
            dishes = [dish for (day, meal_id, _), dish in grouped.items() if day == menu_date and meal_id == meal["meal_type_id"]]
            dishes.sort(key=lambda item: (item["sort_order"], str(item["menu_dish_id"])))
            day_meals.append({**meal, "dishes": dishes, "anomalies": []})
        days.append({"menu_date": menu_date, "meals": day_meals, "anomalies": []})

    columns = [{
        "id": column.id,
        "menu_meal_type_id": column.menu_meal_type_id,
        "name": column.name,
        "sort_order": column.sort_order,
    } for column in layout["meal_type_columns"]]
    return {
        "menu": {"menu_id": menu_id, "menu_name": menu["menu_name"]},
        "days": days,
        "meal_type_columns": columns,
        "report_title": f'{menu["menu_name"]} 調整後廚房配料表',
        "preserve_ingredient_units": True,
    }
