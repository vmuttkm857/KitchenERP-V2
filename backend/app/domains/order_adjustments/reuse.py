from collections import defaultdict
from datetime import date

from app.shared.domain.quantities import convert_quantity, quantize_quantity


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _menu_starts(source_menus):
    return {str(menu["menu_id"]): _date(menu["start_date"]) for menu in source_menus}


def _meal(value):
    return value.strip().casefold()


def build_reuse_preview(previous_lines, current_lines, previous_menus, current_menus, menu_pairs):
    """Compare saved source lines without relying on copied MenuDish UUIDs or row positions."""
    previous_starts = _menu_starts(previous_menus)
    current_starts = _menu_starts(current_menus)
    previous_by_current = {str(pair.current_menu_id): str(pair.previous_menu_id) for pair in menu_pairs}
    candidates = defaultdict(list)
    for line in previous_lines:
        menu_id = str(line.source_menu_id)
        start = previous_starts.get(menu_id)
        if start is None:
            continue
        key = (
            menu_id,
            (_date(line.requirement_date) - start).days,
            _meal(line.meal_type_name_snapshot),
            str(line.source_dish_id),
            str(line.source_dish_ingredient_id),
        )
        candidates[key].append(line)

    results = []
    for current in current_lines:
        current_menu_id = str(current.source_menu_id)
        previous_menu_id = previous_by_current.get(current_menu_id)
        start = current_starts.get(current_menu_id)
        matches = []
        if previous_menu_id is not None and start is not None:
            key = (
                previous_menu_id,
                (_date(current.requirement_date) - start).days,
                _meal(current.meal_type_name_snapshot),
                str(current.source_dish_id),
                str(current.source_dish_ingredient_id),
            )
            matches = candidates.get(key, [])

        status = "no_match"
        reasons = []
        previous = None
        reused_quantity = None
        reused_unit = None
        if not matches:
            reasons.append("NO_MATCHING_OCCURRENCE")
        elif len(matches) > 1:
            status = "ambiguous"
            reasons.append("MULTIPLE_MATCHING_OCCURRENCES")
        else:
            previous = matches[0]
            if previous.adjusted_quantity is None:
                reasons.append("NO_REUSABLE_ADJUSTMENT")
            elif previous.source_ingredient_id != current.source_ingredient_id:
                reasons.append("INGREDIENT_CHANGED")
            else:
                converted_system = convert_quantity(previous.system_quantity, previous.system_unit, current.system_unit)
                explicit_adjusted_unit = getattr(previous, "adjusted_unit", None)
                previous_adjusted_unit = explicit_adjusted_unit or previous.system_unit
                converted_adjusted = convert_quantity(previous.adjusted_quantity, previous_adjusted_unit, current.system_unit)
                if not converted_system.convertible or converted_system.quantity is None or not converted_adjusted.convertible or converted_adjusted.quantity is None:
                    reasons.append("UNIT_INCOMPATIBLE")
                else:
                    if explicit_adjusted_unit is None:
                        reused_quantity = quantize_quantity(converted_adjusted.quantity)
                        reused_unit = current.system_unit
                    else:
                        reused_quantity = quantize_quantity(previous.adjusted_quantity)
                        reused_unit = explicit_adjusted_unit
                    if previous.source_supplier_id != current.source_supplier_id:
                        status = "reference_only"
                        reasons.append("SUPPLIER_CHANGED")
                    elif current.adjusted_quantity is not None:
                        status = "reference_only"
                        reasons.append("CURRENT_ALREADY_ADJUSTED")
                    elif quantize_quantity(converted_system.quantity) != quantize_quantity(current.system_quantity):
                        status = "reference_only"
                        reasons.append("SYSTEM_QUANTITY_CHANGED")
                    else:
                        status = "safe_to_reuse"

        results.append({
            "status": status,
            "reason_codes": reasons,
            "current_line_id": current.id,
            "previous_line_id": previous.id if previous else None,
            "current_menu_id": current.source_menu_id,
            "requirement_date": current.requirement_date,
            "meal_name": current.meal_type_name_snapshot,
            "dish_name": current.dish_name_snapshot,
            "ingredient_name": current.ingredient_name_snapshot,
            "current_system_quantity": current.system_quantity,
            "current_system_unit": current.system_unit,
            "current_adjusted_quantity": current.adjusted_quantity,
            "current_adjusted_unit": getattr(current,"adjusted_unit",None),
            "previous_system_quantity": previous.system_quantity if previous else None,
            "previous_system_unit": previous.system_unit if previous else None,
            "previous_adjusted_quantity": previous.adjusted_quantity if previous else None,
            "previous_adjusted_unit": getattr(previous,"adjusted_unit",None) if previous else None,
            "reused_quantity": reused_quantity,
            "reused_unit": reused_unit,
        })
    return results
