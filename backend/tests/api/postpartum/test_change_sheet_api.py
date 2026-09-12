import uuid
from datetime import date

from sqlalchemy import delete, event, select

from app.domains.menus.models import MenuDish
from app.domains.postpartum.change_sheet import build_daily_change_sheet
from app.domains.postpartum.models import (
    PostpartumConflictHandling, PostpartumReplacementGroup, PostpartumRestrictionGroup,
)
from app.domains.postpartum.meals import MEAL_VALUES
from tests.api.postpartum.test_menu_conflicts_api import (
    TARGET_DATE, auth, configure_conflict_scenario, create_case,
)


def _path(meal="lunch"):
    return f"/api/v1/postpartum/change-sheet?target_date={TARGET_DATE}&postpartum_meal={meal}"


def _daily_path(target_date=TARGET_DATE):
    return f"/api/v1/postpartum/change-sheet/daily?target_date={target_date}"


def _items(evaluation, case_id):
    dishes = {item["menu_dish_id"]: item for item in evaluation["menu_dishes"]}
    return [{
        "case_id": item["case_id"], "original_menu_dish_id": item["menu_dish_id"],
        "original_dish_id": dishes[item["menu_dish_id"]]["dish"]["id"],
    } for item in evaluation["case_dish_results"] if (
        item["case_id"] == case_id and item["outcome"] == "conflict"
    )]


def _configured_handlings(client, db_session):
    headers, first_case, _, _, dishes = configure_conflict_scenario(client, db_session)
    second_case = create_case(client, headers, "P-004", status="active")
    group_ids = list(db_session.scalars(select(PostpartumRestrictionGroup.id)))
    response = client.put(
        f"/api/v1/postpartum/cases/{second_case['id']}/restriction-groups", headers=headers,
        json={"restriction_group_ids": [str(item) for item in group_ids]},
    )
    assert response.status_code == 200, response.text
    evaluation = client.get(
        f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    ).json()
    first_items = _items(evaluation, first_case["id"])
    second_items = _items(evaluation, second_case["id"])
    assert len(first_items) >= 2 and len(second_items) >= 2
    created = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "replacement_dish_id": dishes[2]["id"], "items": [*first_items[:2], second_items[1]],
        "note": "共同替代備註",
    })
    assert created.status_code == 201, created.text
    acknowledged = client.post("/api/v1/postpartum/conflict-acknowledgements", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "item": second_items[0], "note": "人工確認備註",
    })
    assert acknowledged.status_code == 201, acknowledged.text
    return headers, first_case, second_case, first_items, second_items, created.json(), acknowledged.json()


def test_empty_change_sheet_and_all_canonical_meals(client, db_session):
    headers = auth(client, db_session)
    for meal in MEAL_VALUES:
        response = client.get(_path(meal), headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["postpartum_meal"] == meal
        assert body["replacement_groups"] == []
        assert body["manual_acknowledgements"] == []
        assert body["requires_reconfirmation"] == []
        assert body["summary"] == {
            "replacement_group_count": 0, "replacement_item_count": 0,
            "manual_acknowledgement_count": 0, "requires_reconfirmation_count": 0,
        }
    assert client.get(_path("brunch"), headers=headers).status_code == 422
    assert client.get(
        "/api/v1/postpartum/change-sheet?target_date=not-a-date&postpartum_meal=lunch",
        headers=headers,
    ).status_code == 422


def test_change_sheet_group_quantity_reasons_acknowledgement_and_determinism(client, db_session):
    headers, first_case, second_case, _, _, group, acknowledgement = _configured_handlings(client, db_session)
    direct_group = db_session.scalar(select(PostpartumRestrictionGroup).where(
        PostpartumRestrictionGroup.name == "直接菜色",
    ))
    assert client.post(
        f"/api/v1/postpartum/restriction-groups/{direct_group.id}/deactivate", headers=headers,
    ).status_code == 200
    response = client.get(_path(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meal_label"] == "午餐"
    assert body["summary"] == {
        "replacement_group_count": 1, "replacement_item_count": 3,
        "manual_acknowledgement_count": 1, "requires_reconfirmation_count": 0,
    }
    replacement = body["replacement_groups"][0]
    assert replacement["group_id"] == group["id"]
    assert replacement["quantity"] == 3
    assert replacement["case_rooms"] == [first_case["current_room"], second_case["current_room"]]
    assert len(replacement["cases"]) == 2
    assert replacement["note"] == "共同替代備註"
    assert len({item["original_dish"]["id"] for item in replacement["items"]}) == 2
    assert all(item["replacement_dish"]["id"] == group["replacement_dish"]["id"] for item in replacement["items"])
    assert {value["name"] for item in replacement["items"] for value in item["restriction_groups"]} >= {
        "直接菜色", "不牛",
    }
    manual = body["manual_acknowledgements"][0]
    assert manual["handling_id"] == acknowledgement["id"]
    assert manual["case_id"] == second_case["id"]
    assert manual["note"] == "人工確認備註"
    assert manual["status"] == "manually_acknowledged"
    assert client.get(_path(), headers=headers).json() == body


def test_only_stale_replacement_item_requires_reconfirmation(client, db_session):
    headers, _, _, first_items, _, group, acknowledgement = _configured_handlings(client, db_session)
    assert client.post(
        f"/api/v1/postpartum/conflict-acknowledgements/{acknowledgement['id']}/cancel",
        headers=headers,
    ).status_code == 204
    stale_menu_dish_id = first_items[0]["original_menu_dish_id"]
    db_session.execute(delete(MenuDish).where(MenuDish.id == stale_menu_dish_id))
    db_session.commit()

    response = client.get(_path(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    replacement = body["replacement_groups"][0]
    assert replacement["group_id"] == group["id"]
    assert replacement["quantity"] == 3
    assert replacement["status"] == "requires_reconfirmation"
    assert replacement["review_needed"] is True
    assert [item["status"] for item in replacement["items"]].count("requires_reconfirmation") == 1
    assert [item["status"] for item in replacement["items"]].count("replaced") == 2
    stale_item = next(item for item in replacement["items"] if item["status"] == "requires_reconfirmation")
    current_items = [item for item in replacement["items"] if item["status"] == "replaced"]
    assert stale_item["original_menu_dish_id"] == stale_menu_dish_id
    assert stale_item["review_needed"] is True
    assert "ORIGINAL_MENU_DISH_STALE" in {item["code"] for item in stale_item["warnings"]}
    assert all(item["review_needed"] is False and item["warnings"] == [] for item in current_items)
    assert body["manual_acknowledgements"] == []
    assert len(body["requires_reconfirmation"]) == 1
    assert body["summary"]["requires_reconfirmation_count"] == 1
    assert body["requires_reconfirmation"][0]["original_menu_dish_id"] == stale_menu_dish_id
    assert "ORIGINAL_MENU_DISH_STALE" in {item["code"] for item in body["warnings"]}


def test_stale_manual_acknowledgement_remains_and_requires_reconfirmation(client, db_session):
    headers, _, _, _, second_items, group, acknowledgement = _configured_handlings(client, db_session)
    assert client.post(
        f"/api/v1/postpartum/replacement-groups/{group['id']}/cancel", headers=headers,
    ).status_code == 204
    stale_menu_dish_id = second_items[0]["original_menu_dish_id"]
    db_session.execute(delete(MenuDish).where(MenuDish.id == stale_menu_dish_id))
    db_session.commit()

    response = client.get(_path(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replacement_groups"] == []
    assert body["manual_acknowledgements"][0]["handling_id"] == acknowledgement["id"]
    assert body["manual_acknowledgements"][0]["status"] == "requires_reconfirmation"
    assert len(body["requires_reconfirmation"]) == 1
    assert body["requires_reconfirmation"][0]["handling_type"] == "manual_acknowledgement"
    assert body["summary"]["requires_reconfirmation_count"] == 1


def test_change_sheet_uses_fixed_read_queries_and_never_writes(client, db_session, monkeypatch):
    headers, *_ = _configured_handlings(client, db_session)
    statements = []
    engine = db_session.get_bind()

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    def reject_commit():
        raise AssertionError("read endpoint must not commit")

    monkeypatch.setattr(db_session, "commit", reject_commit)
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get(_path(), headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    writes = [item for item in statements if item.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
    assert len(selects) <= 15  # auth + fixed handling/conflict preload + one batch case lookup
    assert writes == []


def test_daily_change_sheet_always_returns_six_canonical_empty_meals(client, db_session):
    headers = auth(client, db_session)
    response = client.get(_daily_path(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_date"] == TARGET_DATE
    assert [item["postpartum_meal"] for item in body["meals"]] == list(MEAL_VALUES)
    assert [item["meal_label"] for item in body["meals"]] == [
        "早餐", "早點", "午餐", "午點", "晚餐", "晚點",
    ]
    assert all(item["has_changes"] is False for item in body["meals"])
    assert all(item["replacement_groups"] == [] for item in body["meals"])
    assert body["summary"] == {
        "replacement_group_count": 0, "replacement_item_count": 0,
        "manual_acknowledgement_count": 0, "requires_reconfirmation_count": 0,
    }
    assert body["warnings"] == []
    # A warning on its own is informational and must not turn an empty meal into a change.
    meals = body["meals"]
    meals[0]["warnings"] = [{"code": "INFO_ONLY", "message": "僅供說明"}]
    warning_only = build_daily_change_sheet(TARGET_DATE, meals)
    assert warning_only["meals"][0]["has_changes"] is False
    assert warning_only["warnings"][0]["code"] == "INFO_ONLY"
    assert client.get(_daily_path("not-a-date"), headers=headers).status_code == 422


def test_daily_change_sheet_aggregates_lunch_without_recounting_quantity(client, db_session):
    headers, _, _, _, _, group, acknowledgement = _configured_handlings(client, db_session)
    response = client.get(_daily_path(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    meals = {item["postpartum_meal"]: item for item in body["meals"]}
    assert meals["lunch"]["has_changes"] is True
    assert all(meals[meal]["has_changes"] is False for meal in MEAL_VALUES if meal != "lunch")
    assert meals["lunch"]["replacement_groups"][0]["group_id"] == group["id"]
    assert meals["lunch"]["replacement_groups"][0]["quantity"] == 3
    assert meals["lunch"]["summary"] == {
        "replacement_group_count": 1, "replacement_item_count": 3,
        "manual_acknowledgement_count": 1, "requires_reconfirmation_count": 0,
    }
    assert meals["lunch"]["manual_acknowledgements"][0]["handling_id"] == acknowledgement["id"]
    assert body["summary"] == meals["lunch"]["summary"]
    assert client.get(_daily_path(), headers=headers).json() == body


def test_daily_change_sheet_counts_only_the_truly_stale_group_item(client, db_session):
    headers, _, _, first_items, _, _, acknowledgement = _configured_handlings(client, db_session)
    assert client.post(
        f"/api/v1/postpartum/conflict-acknowledgements/{acknowledgement['id']}/cancel",
        headers=headers,
    ).status_code == 204
    db_session.execute(delete(MenuDish).where(
        MenuDish.id == first_items[0]["original_menu_dish_id"],
    ))
    db_session.commit()

    body = client.get(_daily_path(), headers=headers).json()
    lunch = next(item for item in body["meals"] if item["postpartum_meal"] == "lunch")
    assert lunch["replacement_groups"][0]["quantity"] == 3
    assert lunch["replacement_groups"][0]["status"] == "requires_reconfirmation"
    assert [item["status"] for item in lunch["replacement_groups"][0]["items"]].count(
        "requires_reconfirmation",
    ) == 1
    assert len(lunch["requires_reconfirmation"]) == 1
    assert lunch["summary"]["requires_reconfirmation_count"] == 1
    assert body["summary"]["requires_reconfirmation_count"] == 1


def test_daily_change_sheet_stale_acknowledgement_stays_in_its_meal(client, db_session):
    headers, _, _, _, second_items, group, acknowledgement = _configured_handlings(client, db_session)
    assert client.post(
        f"/api/v1/postpartum/replacement-groups/{group['id']}/cancel", headers=headers,
    ).status_code == 204
    db_session.execute(delete(MenuDish).where(
        MenuDish.id == second_items[0]["original_menu_dish_id"],
    ))
    db_session.commit()

    body = client.get(_daily_path(), headers=headers).json()
    lunch = next(item for item in body["meals"] if item["postpartum_meal"] == "lunch")
    assert lunch["manual_acknowledgements"][0]["handling_id"] == acknowledgement["id"]
    assert lunch["manual_acknowledgements"][0]["status"] == "requires_reconfirmation"
    assert lunch["requires_reconfirmation"][0]["handling_type"] == "manual_acknowledgement"
    assert all(
        item["requires_reconfirmation"] == []
        for item in body["meals"] if item["postpartum_meal"] != "lunch"
    )


def test_daily_change_sheet_keeps_replacements_from_multiple_meals_separate(client, db_session):
    headers, _, _, _, second_items, group, acknowledgement = _configured_handlings(client, db_session)
    assert client.post(
        f"/api/v1/postpartum/conflict-acknowledgements/{acknowledgement['id']}/cancel",
        headers=headers,
    ).status_code == 204
    source_group = db_session.get(PostpartumReplacementGroup, uuid.UUID(group["id"]))
    breakfast_group = PostpartumReplacementGroup(
        id=uuid.uuid4(), target_date=date.fromisoformat(TARGET_DATE), postpartum_meal="breakfast",
        replacement_dish_id=uuid.UUID(group["replacement_dish"]["id"]), note="早餐異動",
        created_by=source_group.created_by, updated_by=source_group.updated_by,
    )
    db_session.add(breakfast_group)
    db_session.flush()
    db_session.add(PostpartumConflictHandling(
        id=uuid.uuid4(), target_date=date.fromisoformat(TARGET_DATE), postpartum_meal="breakfast",
        case_id=uuid.UUID(second_items[0]["case_id"]),
        original_menu_dish_id=uuid.UUID(second_items[0]["original_menu_dish_id"]),
        original_dish_id=uuid.UUID(second_items[0]["original_dish_id"]),
        replacement_group_id=breakfast_group.id,
        created_by=source_group.created_by, updated_by=source_group.updated_by,
    ))
    db_session.commit()

    body = client.get(_daily_path(), headers=headers).json()
    meals = {item["postpartum_meal"]: item for item in body["meals"]}
    assert meals["breakfast"]["has_changes"] is True
    assert meals["breakfast"]["replacement_groups"][0]["quantity"] == 1
    assert meals["lunch"]["has_changes"] is True
    assert meals["lunch"]["replacement_groups"][0]["quantity"] == 3
    assert body["summary"]["replacement_group_count"] == 2
    assert body["summary"]["replacement_item_count"] == 4


def test_daily_change_sheet_uses_one_fixed_read_preload_and_never_writes(client, db_session, monkeypatch):
    headers, *_ = _configured_handlings(client, db_session)
    statements = []
    engine = db_session.get_bind()

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    def reject_commit():
        raise AssertionError("daily read endpoint must not commit")

    monkeypatch.setattr(db_session, "commit", reject_commit)
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get(_daily_path(), headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    writes = [item for item in statements if item.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
    assert len(selects) <= 15  # auth + one all-meal handling/conflict preload + one batch case lookup
    assert writes == []
