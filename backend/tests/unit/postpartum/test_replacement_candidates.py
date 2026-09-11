import uuid

from app.domains.postpartum.conflicts import evaluate_replacement_candidates


def test_candidate_conflict_and_empty_recipe_statuses_are_deterministic():
    case_id = uuid.uuid4()
    group_id = uuid.uuid4()
    blocked_id = uuid.uuid4()
    empty_id = uuid.uuid4()
    groups = {group_id: {
        "id": group_id, "name": "不牛", "color": "#AA0000", "notes": None, "is_active": True,
    }}
    common = dict(
        case_ids=[case_id], groups_by_case={case_id: [group_id]}, groups=groups,
        dish_targets_by_group={group_id: {blocked_id: {
            "id": blocked_id, "code": "1", "name": "牛肉料理", "is_active": True,
        }}}, ingredient_targets_by_group={group_id: {}},
        recipe_ingredients_by_dish={blocked_id: {}, empty_id: {}},
    )
    results = evaluate_replacement_candidates(candidate_dishes=[
        {"id": blocked_id, "code": "1", "name": "牛肉料理", "is_active": True},
        {"id": empty_id, "code": "2", "name": "無配方菜", "is_active": True},
    ], **common)
    assert [item["status"] for item in results] == ["conflict", "insufficient_recipe_data"]
    assert results[0]["case_results"][0]["reasons"][0]["type"] == "direct_dish"
    assert results[1]["review_needed"] is True
