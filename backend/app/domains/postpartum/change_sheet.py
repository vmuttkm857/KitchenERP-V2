from app.domains.postpartum.meals import MEAL_LABELS


def _natural_key(value):
    text = value or ""
    if text.isdigit():
        return 0, int(text), len(text), text.casefold(), text
    return 1, 0, 0, text.casefold(), text


def _warning_key(item):
    return tuple(str(item.get(key) or "") for key in (
        "code", "message", "case_id", "menu_dish_id", "restriction_group_id", "ingredient_id", "target_id",
    ))


def _target_sort(item):
    return _natural_key(item.get("code")), (item.get("name") or "").casefold(), str(item.get("id"))


def _item_sort(item):
    return (
        _natural_key(item["current_room"]), (item["case_number"] or "").casefold(),
        _natural_key(item["original_dish"]["code"]),
        item["original_dish"]["name"].casefold(), str(item["handling_id"]),
    )


def _restriction_groups(evaluation):
    values = {}
    for result in evaluation.get("case_dish_results", []):
        key = result["case_id"], result["menu_dish_id"]
        groups = {}
        for reason in result.get("reasons", []):
            group = reason["restriction_group"]
            groups[group["id"]] = {"id": group["id"], "name": group["name"], "color": group["color"]}
        values[key] = sorted(groups.values(), key=lambda item: (item["name"].casefold(), str(item["id"])))
    return values


def build_change_sheet(target_date, postpartum_meal, handling_view, case_models, evaluation):
    case_by_id = {item.id: item for item in case_models}
    restriction_by_item = _restriction_groups(evaluation)
    warnings = {}

    def case_summary(case_id):
        item = case_by_id[case_id]
        return {
            "case_id": item.id, "case_number": item.case_number,
            "name": item.name, "current_room": item.current_room,
        }

    def item_view(item, replacement_dish=None):
        case = case_summary(item["case_id"])
        status = item["status"]
        for warning in item["warnings"]:
            warnings[_warning_key(warning)] = warning
        return {
            "handling_id": item["id"], "case_id": case["case_id"],
            "case_number": case["case_number"], "case_name": case["name"],
            "current_room": case["current_room"],
            "original_menu_dish_id": item["original_menu_dish_id"],
            "original_dish": item["original_dish"],
            **({"replacement_dish": replacement_dish} if replacement_dish is not None else {}),
            "restriction_groups": restriction_by_item.get((item["case_id"], item["original_menu_dish_id"]), []),
            "status": status, "review_needed": status == "requires_reconfirmation",
            "warnings": item["warnings"],
        }

    replacement_groups = []
    requires_reconfirmation = []
    for group in handling_view["replacement_groups"]:
        items = [item_view(item, group["replacement_dish"]) for item in group["items"]]
        items.sort(key=_item_sort)
        cases = {item["case_id"]: {
            "case_id": item["case_id"], "case_number": item["case_number"],
            "name": item["case_name"], "current_room": item["current_room"],
        } for item in items}
        case_values = sorted(cases.values(), key=lambda item: (
            _natural_key(item["current_room"]), item["case_number"].casefold(), str(item["case_id"]),
        ))
        rooms = sorted({item["current_room"] for item in items}, key=_natural_key)
        for warning in group["warnings"]:
            warnings[_warning_key(warning)] = warning
        value = {
            "group_id": group["id"], "replacement_dish": group["replacement_dish"],
            "quantity": len(items), "case_rooms": rooms, "cases": case_values, "items": items,
            "note": group["note"], "status": group["status"],
            "review_needed": group["review_needed"] or group["status"] == "requires_reconfirmation",
            "warnings": group["warnings"],
        }
        replacement_groups.append(value)
        if group["status"] == "requires_reconfirmation":
            for item in items:
                if item["status"] != "requires_reconfirmation":
                    continue
                requires_reconfirmation.append({
                    "handling_type": "replacement", "group_id": group["id"], **item,
                })

    replacement_groups.sort(key=lambda item: (*_target_sort(item["replacement_dish"]), str(item["group_id"])))

    acknowledgements = []
    for item in handling_view["manual_acknowledgements"]:
        value = item_view(item)
        value.update({"note": item["note"]})
        acknowledgements.append(value)
        if value["status"] == "requires_reconfirmation":
            requires_reconfirmation.append({
                "handling_type": "manual_acknowledgement", "group_id": None, **value,
            })
    acknowledgements.sort(key=_item_sort)
    requires_reconfirmation.sort(key=lambda item: (*_item_sort(item), item["handling_type"], str(item["group_id"] or "")))

    return {
        "target_date": target_date, "postpartum_meal": postpartum_meal,
        "meal_label": MEAL_LABELS[postpartum_meal],
        "summary": {
            "replacement_group_count": len(replacement_groups),
            "replacement_item_count": sum(item["quantity"] for item in replacement_groups),
            "manual_acknowledgement_count": len(acknowledgements),
            "requires_reconfirmation_count": len(requires_reconfirmation),
        },
        "replacement_groups": replacement_groups,
        "manual_acknowledgements": acknowledgements,
        "requires_reconfirmation": requires_reconfirmation,
        "warnings": [warnings[key] for key in sorted(warnings)],
    }


def build_daily_change_sheet(target_date, meals):
    summary_keys = (
        "replacement_group_count", "replacement_item_count",
        "manual_acknowledgement_count", "requires_reconfirmation_count",
    )
    summary = {key: sum(item["summary"][key] for item in meals) for key in summary_keys}
    warnings = {}
    values = []
    for item in meals:
        value = {
            **item,
            "has_changes": bool(
                item["replacement_groups"]
                or item["manual_acknowledgements"]
                or item["requires_reconfirmation"]
            ),
        }
        values.append(value)
        for warning in item["warnings"]:
            warnings[_warning_key(warning)] = warning
    return {
        "target_date": target_date,
        "summary": summary,
        "meals": values,
        "warnings": [warnings[key] for key in sorted(warnings)],
    }
