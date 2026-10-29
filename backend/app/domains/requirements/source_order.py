"""Versioned export positions, captured with the source graph, never reconstructed live."""
from collections import defaultdict
from types import SimpleNamespace
from uuid import UUID

from app.domains.menus.placement import menu_dish_visual_rows


def trusted_source_order(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        return None
    for key, minimum in (("meal_sort_order", 1), ("meal_position", 1), ("visual_position", 1),
                         ("dish_sort_order", 1), ("ingredient_sort_order", 0),
                         ("ingredient_position", 1)):
        if type(value.get(key)) is not int or value[key] < minimum:
            return None
    column = value.get("column_sort_order")
    if column is not None and (type(column) is not int or column < 1):
        return None
    try:
        for key in ("meal_type_id", "menu_dish_id", "recipe_detail_id"):
            UUID(str(value[key]))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    return dict(value)


def attach_source_order(rows):
    """Use the complete column layout from the SAME SELECT as the source rows.

    Missing layout means a legacy/frozen source, not permission to infer columns.
    Placement includes other suppliers, empty columns, fallback and overflow dishes.
    """
    result = [dict(row) for row in rows]
    slots = defaultdict(list)
    meals = defaultdict(dict)
    for row in result:
        if "_menu_columns" in row:
            slots[(row["menu_id"], row["menu_date"], row["meal_type_id"])].append(row)
            meals[row["menu_id"]][row["meal_type_id"]] = row["meal_type_sort_order"]
    # Capture the menu API's existing sort_order/id tie rule as a numeric rank.
    # Exports never sort by a mutable name or use an ID as a stand-in position.
    meal_positions = {
        (menu, meal): index
        for menu, definitions in meals.items()
        for index, (meal, _) in enumerate(sorted(definitions.items(), key=lambda item: (item[1], item[0])), 1)
    }
    for slot in slots.values():
        columns = [SimpleNamespace(id=UUID(str(column["id"])), sort_order=column["sort_order"])
                   for column in (slot[0]["_menu_columns"] or [])]
        dishes = {}
        for row in slot:
            dishes.setdefault(row["menu_dish_id"], SimpleNamespace(
                id=row["menu_dish_id"], sort_order=row["menu_dish_sort_order"],
                menu_meal_type_column_id=row["menu_meal_type_column_id"]))
        placed = menu_dish_visual_rows(columns, list(dishes.values()))
        column_orders = {column.id: column.sort_order for column in columns}
        positions = {entry.dish.id: (index, column_orders.get(entry.column_id))
                     for index, entry in enumerate(placed, 1) if entry.dish is not None}
        ingredients = defaultdict(dict)
        for row in slot:
            if row["recipe_detail_id"] is not None:
                ingredients[row["menu_dish_id"]][row["recipe_detail_id"]] = row["dish_ingredient_sort_order"]
        recipe_positions = {
            (dish, detail): index
            for dish, details in ingredients.items()
            for index, (detail, _) in enumerate(sorted(details.items(), key=lambda item: (item[1], item[0])), 1)
        }
        for row in slot:
            if row["recipe_detail_id"] is None:
                continue
            position, column_order = positions[row["menu_dish_id"]]
            row["source_order"] = {
                "version": 1, "meal_type_id": str(row["meal_type_id"]),
                "meal_sort_order": row["meal_type_sort_order"],
                "meal_position": meal_positions[row["menu_id"], row["meal_type_id"]],
                "visual_position": position, "column_sort_order": column_order,
                "menu_dish_id": str(row["menu_dish_id"]),
                "dish_sort_order": row["menu_dish_sort_order"],
                "recipe_detail_id": str(row["recipe_detail_id"]),
                "ingredient_sort_order": row["dish_ingredient_sort_order"],
                "ingredient_position": recipe_positions[row["menu_dish_id"], row["recipe_detail_id"]],
            }
    for row in result:
        row.pop("_menu_columns", None)
    return result


def saved_source_orders(items):
    """Index frozen JSON only; conflicting/absent provenance cannot supply an order."""
    result, conflicts = {}, set()
    for item in items:
        sources = item.get("source_summary", []) if isinstance(item, dict) else getattr(item, "source_summary", [])
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict):
                continue
            order = trusted_source_order(source.get("source_order"))
            if order is None:
                continue
            key = (str(source.get("menu_id")), str(source.get("requirement_date")),
                   order["menu_dish_id"], order["recipe_detail_id"])
            if key in result and result[key] != order:
                conflicts.add(key)
            result[key] = order
    return {key: value for key, value in result.items() if key not in conflicts}


def order_for_line(orders, line):
    key = (str(line.source_menu_id), str(line.requirement_date),
           str(line.source_menu_dish_id), str(line.source_dish_ingredient_id))
    order = orders.get(key)
    if order and order["meal_type_id"] == str(line.source_meal_type_id):
        return dict(order)
    return None
