from datetime import date
from decimal import Decimal
import uuid

from app.shared.domain.quantities import convert_quantity


def _value(value):
    if isinstance(value, Decimal): return format(value, "f")
    if isinstance(value, (date, uuid.UUID)): return str(value)
    return value


def _dish_from_saved(line):
    return {
        "source_menu_id": str(line.source_menu_id), "source_menu_dish_id": str(line.source_menu_dish_id),
        "source_dish_id": str(line.source_dish_id), "dish_name": line.dish_name_snapshot,
        "requirement_date": line.requirement_date.isoformat(), "source_meal_type_id": str(line.source_meal_type_id),
        "meal_name": line.meal_type_name_snapshot,
        "source_menu_meal_type_column_id": str(line.source_menu_meal_type_column_id) if line.source_menu_meal_type_column_id else None,
        "sort_order": line.menu_dish_sort_order_snapshot, "diner_count": line.diner_count_snapshot,
    }


def _dish_from_live(row):
    return {
        "source_menu_id": str(row["menu_id"]), "source_menu_dish_id": str(row["menu_dish_id"]),
        "source_dish_id": str(row["dish_id"]), "dish_name": row["dish_name"],
        "requirement_date": row["menu_date"].isoformat(), "source_meal_type_id": str(row["meal_type_id"]),
        "meal_name": row["meal_type_name"],
        "source_menu_meal_type_column_id": str(row["menu_meal_type_column_id"]) if row["menu_meal_type_column_id"] else None,
        "sort_order": row["menu_dish_sort_order"], "diner_count": row["diner_count"],
    }


def _position(dish):
    return (
        dish["source_menu_id"], dish["requirement_date"], dish["source_meal_type_id"],
        dish["source_menu_meal_type_column_id"], dish["sort_order"],
    )


def _saved_line(line):
    return {
        "line_id": str(line.id),
        "source_line_key": line.source_line_key,
        "source_menu_dish_id": str(line.source_menu_dish_id), "source_dish_id": str(line.source_dish_id),
        "dish_name": line.dish_name_snapshot,
        "source_dish_ingredient_id": str(line.source_dish_ingredient_id),
        "source_ingredient_id": str(line.source_ingredient_id), "ingredient_name": line.ingredient_name_snapshot,
        "system_quantity": format(line.system_quantity, "f"), "system_unit": line.system_unit,
        "adjusted_quantity": None if line.adjusted_quantity is None else format(line.adjusted_quantity, "f"),
        "adjusted_unit": line.adjusted_unit,
        "effective_quantity": format(line.adjusted_quantity if line.adjusted_quantity is not None else line.system_quantity, "f"),
        "effective_unit": line.adjusted_unit if line.adjusted_quantity is not None else line.system_unit,
    }


def _live_line(plan):
    return {
        "source_line_key": plan["source_line_key"],
        "source_menu_dish_id": str(plan["source_menu_dish_id"]), "source_dish_id": str(plan["source_dish_id"]),
        "dish_name": plan["dish_name_snapshot"],
        "source_dish_ingredient_id": str(plan["source_dish_ingredient_id"]),
        "source_ingredient_id": str(plan["source_ingredient_id"]), "ingredient_name": plan["ingredient_name_snapshot"],
        "system_quantity": format(plan["system_quantity"], "f"), "system_unit": plan["system_unit"],
    }


def _same_identity(line, plan):
    return (
        line.source_menu_dish_id == plan["source_menu_dish_id"]
        and line.source_dish_id == plan["source_dish_id"]
        and line.source_dish_ingredient_id == plan["source_dish_ingredient_id"]
        and line.source_ingredient_id == plan["source_ingredient_id"]
    )


def _line_change_types(line, plan):
    changes=[]
    if line.dish_name_snapshot != plan["dish_name_snapshot"]: changes.append("dish_name_changed")
    if line.ingredient_name_snapshot != plan["ingredient_name_snapshot"]: changes.append("ingredient_name_changed")
    if (
        line.source_menu_day_id != plan["source_menu_day_id"] or line.requirement_date != plan["requirement_date"]
        or line.source_meal_type_id != plan["source_meal_type_id"]
        or line.source_menu_meal_type_column_id != plan["source_menu_meal_type_column_id"]
        or line.menu_dish_sort_order_snapshot != plan["menu_dish_sort_order_snapshot"]
    ): changes.append("menu_position_changed")
    if line.diner_count_snapshot != plan["diner_count_snapshot"]: changes.append("diner_count_changed")
    if (
        line.quantity_per_person_snapshot != plan["quantity_per_person_snapshot"]
        or line.loss_rate_snapshot != plan["loss_rate_snapshot"]
        or line.system_quantity != plan["system_quantity"]
    ): changes.append("reference_quantity_changed")
    if line.recipe_unit_snapshot != plan["recipe_unit_snapshot"] or line.system_unit != plan["system_unit"]:
        changes.append("unit_changed")
    metadata=(
        (line.menu_name_snapshot, line.meal_type_name_snapshot, line.dish_code_snapshot, line.ingredient_code_snapshot,
         line.source_supplier_id, line.supplier_name_snapshot, line.configured_purchase_unit_snapshot,
         line.package_size_snapshot, line.minimum_order_quantity_snapshot, line.current_price_snapshot)
        !=
        (plan["menu_name_snapshot"], plan["meal_type_name_snapshot"], plan["dish_code_snapshot"], plan["ingredient_code_snapshot"],
         plan["source_supplier_id"], plan["supplier_name_snapshot"], plan["configured_purchase_unit_snapshot"],
         plan["package_size_snapshot"], plan["minimum_order_quantity_snapshot"], plan["current_price_snapshot"])
    )
    if metadata: changes.append("source_metadata_changed")
    return changes


def classify_sync_lines(lines, plans):
    saved_by_key={line.source_line_key:line for line in lines}
    live_by_key={plan["source_line_key"]:plan for plan in plans}
    retained_keys={key for key in set(saved_by_key)&set(live_by_key) if _same_identity(saved_by_key[key],live_by_key[key])}
    return {
        "saved_by_key":saved_by_key,
        "live_by_key":live_by_key,
        "retained_keys":retained_keys,
        "removed_keys":set(saved_by_key)-retained_keys,
        "added_keys":set(live_by_key)-retained_keys,
    }


def build_sync_preview(sheet, lines, live_rows, plans, preview_fingerprint):
    old_dishes={}
    for line in lines: old_dishes.setdefault((line.source_menu_dish_id,line.source_dish_id),_dish_from_saved(line))
    new_dishes={}
    for row in live_rows: new_dishes.setdefault((row["menu_dish_id"],row["dish_id"]),_dish_from_live(row))
    removed_dishes=[old_dishes[key] for key in sorted(set(old_dishes)-set(new_dishes),key=lambda value:tuple(map(str,value)))]
    added_dishes=[new_dishes[key] for key in sorted(set(new_dishes)-set(old_dishes),key=lambda value:tuple(map(str,value)))]

    added_by_position={_position(value):value for value in added_dishes}
    possible_replacements=[]
    for old in removed_dishes:
        current=added_by_position.get(_position(old))
        if current is not None:
            possible_replacements.append({"previous":old,"current":current,"preserves_adjustment":False,"requires_confirmation":True})

    classified=classify_sync_lines(lines,plans)
    saved_by_key=classified["saved_by_key"];live_by_key=classified["live_by_key"]
    retained_keys=classified["retained_keys"];removed_keys=classified["removed_keys"];added_keys=classified["added_keys"]
    removed_ingredients=[{"previous":_saved_line(saved_by_key[key]),"current":None,"preserves_adjustment":False,"requires_confirmation":True} for key in sorted(removed_keys)]
    added_ingredients=[{"previous":None,"current":_live_line(live_by_key[key]),"preserves_adjustment":False,"requires_confirmation":True} for key in sorted(added_keys)]

    line_changes=[];unit_conflicts=[]
    for key in sorted(retained_keys):
        line=saved_by_key[key];plan=live_by_key[key];change_types=_line_change_types(line,plan)
        if change_types:
            value={"source_line_key":key,"change_types":change_types,"previous":_saved_line(line),"current":_live_line(plan),"preserves_adjustment":True,"requires_confirmation":False}
            line_changes.append(value)
        if line.adjusted_quantity is not None:
            conversion=convert_quantity(line.adjusted_quantity,line.adjusted_unit,plan["system_unit"])
            if not conversion.convertible or conversion.quantity is None:
                conflict={"source_line_key":key,"change_types":["unit_conflict"],"previous":_saved_line(line),"current":_live_line(plan),"preserves_adjustment":True,"requires_confirmation":True}
                unit_conflicts.append(conflict)

    summary={
        "added_dishes":len(added_dishes),"removed_dishes":len(removed_dishes),
        "possible_dish_replacements":len(possible_replacements),"added_ingredients":len(added_ingredients),
        "removed_ingredients":len(removed_ingredients),"changed_lines":len(line_changes),"unit_conflicts":len(unit_conflicts),
    }
    return {
        "sheet_id":sheet.id,"status":sheet.status,"lock_version":sheet.lock_version,
        "saved_source_fingerprint":sheet.source_fingerprint,"preview_source_fingerprint":preview_fingerprint,
        "changed":sheet.source_fingerprint!=preview_fingerprint,"summary":summary,
        "added_dishes":added_dishes,"removed_dishes":removed_dishes,"possible_dish_replacements":possible_replacements,
        "added_ingredients":added_ingredients,"removed_ingredients":removed_ingredients,
        "line_changes":line_changes,"unit_conflicts":unit_conflicts,
    }
