import uuid

from app.domains.postpartum.conflicts import evaluate_case_dish_conflicts


def target(value, code, name, active=True):
    return {"id": value, "code": code, "name": name, "is_active": active}


def test_exact_uuid_conflicts_are_aggregated_and_partial_never_reports_safe():
    case_id, dish_id, menu_dish_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ingredient_id = uuid.uuid4()
    direct_group, ingredient_group, note_group = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    groups = {
        direct_group: {"id": direct_group, "name": "不牛菜", "color": "#AA0000", "notes": None, "is_active": True},
        ingredient_group: {"id": ingredient_group, "name": "不牛", "color": "#00AA00", "notes": None, "is_active": False},
        note_group: {"id": note_group, "name": "特殊禁忌", "color": "#0000AA", "notes": "人工確認", "is_active": True},
    }
    dish_target = target(dish_id, "D1", "牛肉湯")
    ingredient_target = target(ingredient_id, "I1", "牛肉", active=False)
    dishes, warnings, results = evaluate_case_dish_conflicts(
        case_ids=[case_id],
        menu_dishes=[{"menu_dish_id": menu_dish_id, "sort_order": 1, "dish_id": dish_id,
                      "dish_code": "D1", "dish_name": "牛肉湯", "dish_is_active": True}],
        groups_by_case={case_id: [direct_group, ingredient_group, note_group]}, groups=groups,
        dish_targets_by_group={direct_group: {dish_id: dish_target}, ingredient_group: {}, note_group: {}},
        ingredient_targets_by_group={direct_group: {}, ingredient_group: {ingredient_id: ingredient_target}, note_group: {}},
        recipe_ingredients_by_dish={dish_id: {ingredient_id: ingredient_target}},
    )
    assert dishes[0]["ingredient_coverage"] == "complete"
    assert {item["code"] for item in warnings[case_id]} == {
        "RESTRICTION_GROUP_INACTIVE", "RESTRICTION_GROUP_NOTE_ONLY",
    }
    assert len(results) == 1
    assert results[0]["outcome"] == "conflict" and results[0]["coverage"] == "partial"
    assert [item["type"] for item in results[0]["reasons"]] == ["direct_dish", "ingredient"]
    assert results[0]["warnings"][0]["code"] == "RESTRICTION_TARGET_INACTIVE"


def test_empty_recipe_keeps_direct_check_but_unknown_when_no_reason():
    case_id = uuid.uuid4()
    direct_group = uuid.uuid4()
    restricted_dish, other_dish = uuid.uuid4(), uuid.uuid4()
    first_menu_dish, second_menu_dish = uuid.uuid4(), uuid.uuid4()
    groups = {direct_group: {
        "id": direct_group, "name": "指定菜禁忌", "color": "#AA0000", "notes": None, "is_active": True,
    }}
    views, _, results = evaluate_case_dish_conflicts(
        case_ids=[case_id],
        menu_dishes=[
            {"menu_dish_id": first_menu_dish, "sort_order": 1, "dish_id": restricted_dish,
             "dish_code": "D1", "dish_name": "禁忌菜", "dish_is_active": True},
            {"menu_dish_id": second_menu_dish, "sort_order": 2, "dish_id": other_dish,
             "dish_code": "D2", "dish_name": "其他菜", "dish_is_active": True},
        ],
        groups_by_case={case_id: [direct_group]}, groups=groups,
        dish_targets_by_group={direct_group: {restricted_dish: target(restricted_dish, "D1", "禁忌菜")}},
        ingredient_targets_by_group={direct_group: {}}, recipe_ingredients_by_dish={},
    )
    assert all(item["ingredient_coverage"] == "partial" for item in views)
    assert [(item["outcome"], item["coverage"]) for item in results] == [
        ("conflict", "partial"), ("unknown", "partial"),
    ]
