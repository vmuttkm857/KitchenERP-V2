from __future__ import annotations

import uuid
from collections.abc import Iterable


def _warning(code: str, message: str, **context) -> dict:
    return {"code": code, "message": message, **context}


def evaluate_case_dish_conflicts(
    *,
    case_ids: Iterable[uuid.UUID],
    menu_dishes: list[dict],
    groups_by_case: dict[uuid.UUID, list[uuid.UUID]],
    groups: dict[uuid.UUID, dict],
    dish_targets_by_group: dict[uuid.UUID, dict[uuid.UUID, dict]],
    ingredient_targets_by_group: dict[uuid.UUID, dict[uuid.UUID, dict]],
    recipe_ingredients_by_dish: dict[uuid.UUID, dict[uuid.UUID, dict]],
) -> tuple[list[dict], dict[uuid.UUID, list[dict]], list[dict]]:
    """Build deterministic presentation results from already batch-loaded UUID maps."""
    case_warnings: dict[uuid.UUID, list[dict]] = {}
    results: list[dict] = []
    for case_id in case_ids:
        warnings = []
        for group_id in groups_by_case.get(case_id, []):
            group = groups[group_id]
            if not group["is_active"]:
                warnings.append(_warning(
                    "RESTRICTION_GROUP_INACTIVE", f"禁忌群組「{group['name']}」已停用",
                    restriction_group_id=group_id,
                ))
            if not dish_targets_by_group.get(group_id) and not ingredient_targets_by_group.get(group_id):
                warnings.append(_warning(
                    "RESTRICTION_GROUP_NOTE_ONLY" if group.get("notes") else "RESTRICTION_GROUP_NO_TARGETS",
                    f"禁忌群組「{group['name']}」無法由菜色或食材關聯自動判定",
                    restriction_group_id=group_id,
                ))
        case_warnings[case_id] = warnings

    dish_views = []
    for menu_dish in menu_dishes:
        dish_id = menu_dish["dish_id"]
        ingredients = recipe_ingredients_by_dish.get(dish_id, {})
        dish_warnings = []
        ingredient_coverage = "complete"
        if not ingredients:
            ingredient_coverage = "partial"
            dish_warnings.append(_warning(
                "DISH_RECIPE_EMPTY", "此菜沒有配方食材，僅能檢查直接菜色禁忌",
                menu_dish_id=menu_dish["menu_dish_id"],
            ))
        if not menu_dish["dish_is_active"]:
            dish_warnings.append(_warning(
                "MENU_DISH_INACTIVE", f"菜色「{menu_dish['dish_name']}」已停用",
                menu_dish_id=menu_dish["menu_dish_id"],
            ))
        for ingredient in ingredients.values():
            if not ingredient["is_active"]:
                dish_warnings.append(_warning(
                    "RECIPE_INGREDIENT_INACTIVE", f"配方食材「{ingredient['name']}」已停用",
                    menu_dish_id=menu_dish["menu_dish_id"], ingredient_id=ingredient["id"],
                ))
        dish_views.append({
            "menu_dish_id": menu_dish["menu_dish_id"],
            "sort_order": menu_dish["sort_order"],
            "dish": {
                "id": dish_id, "code": menu_dish["dish_code"], "name": menu_dish["dish_name"],
                "is_active": menu_dish["dish_is_active"],
            },
            "ingredient_coverage": ingredient_coverage,
            "warnings": dish_warnings,
        })

    for case_id in case_ids:
        group_ids = groups_by_case.get(case_id, [])
        note_only = any(
            not dish_targets_by_group.get(group_id) and not ingredient_targets_by_group.get(group_id)
            for group_id in group_ids
        )
        for menu_dish in menu_dishes:
            dish_id = menu_dish["dish_id"]
            recipe_ingredients = recipe_ingredients_by_dish.get(dish_id, {})
            reasons = []
            warnings = []
            for group_id in group_ids:
                group = groups[group_id]
                restricted_dish = dish_targets_by_group.get(group_id, {}).get(dish_id)
                if restricted_dish is not None:
                    reasons.append({
                        "type": "direct_dish",
                        "restriction_group": group,
                        "matched_target": restricted_dish,
                    })
                    if not restricted_dish["is_active"]:
                        warnings.append(_warning(
                            "RESTRICTION_TARGET_INACTIVE",
                            f"禁忌關聯菜色「{restricted_dish['name']}」已停用",
                            restriction_group_id=group_id, target_id=dish_id,
                        ))
                matching_ingredients = set(recipe_ingredients) & set(
                    ingredient_targets_by_group.get(group_id, {})
                )
                for ingredient_id in sorted(
                    matching_ingredients,
                    key=lambda item: (
                        ingredient_targets_by_group[group_id][item]["code"].lower(),
                        ingredient_targets_by_group[group_id][item]["name"].lower(), str(item),
                    ),
                ):
                    target = ingredient_targets_by_group[group_id][ingredient_id]
                    reasons.append({
                        "type": "ingredient",
                        "restriction_group": group,
                        "matched_target": target,
                    })
                    if not target["is_active"]:
                        warnings.append(_warning(
                            "RESTRICTION_TARGET_INACTIVE",
                            f"禁忌關聯食材「{target['name']}」已停用",
                            restriction_group_id=group_id, target_id=ingredient_id,
                        ))
            partial = not recipe_ingredients or note_only
            results.append({
                "case_id": case_id,
                "menu_dish_id": menu_dish["menu_dish_id"],
                "outcome": "conflict" if reasons else ("unknown" if partial else "no_conflict"),
                "coverage": "partial" if partial else "complete",
                "reasons": reasons,
                "warnings": warnings,
            })

    return dish_views, case_warnings, results
