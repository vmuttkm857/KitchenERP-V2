from sqlalchemy import delete, event, func, select, update

from app.domains.audit.models import AuditLog
from app.domains.postpartum.models import (
    PostpartumConflictHandling, PostpartumReplacementGroup, PostpartumRestrictionGroup,
)
from app.domains.postpartum.repository import PostpartumRepository
from app.domains.menus.models import MenuDish
from app.domains.ingredients.models import Ingredient
from tests.api.postpartum.test_menu_conflicts_api import (
    TARGET_DATE, configure_conflict_scenario, create_case,
)


def _conflict(client, headers):
    response = client.get(
        f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    result = next(item for item in body["case_dish_results"] if item["outcome"] == "conflict")
    dish = next(item for item in body["menu_dishes"] if item["menu_dish_id"] == result["menu_dish_id"])
    return {
        "case_id": result["case_id"], "original_menu_dish_id": result["menu_dish_id"],
        "original_dish_id": dish["dish"]["id"],
    }


def test_candidate_search_create_cancel_and_audit(client, db_session):
    headers, _, _, _, dishes = configure_conflict_scenario(client, db_session)
    item = _conflict(client, headers)
    pending = client.get(
        f"/api/v1/postpartum/conflict-handlings?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    ).json()
    assert {row["status"] for row in pending["conflict_items"]} == {"pending"}
    safe = client.post("/api/v1/dishes", headers=headers, json={
        "code": "CD-99", "name": "安全候選菜", "category_id": dishes[0]["category_id"],
    }).json()
    ginger = db_session.scalar(select(Ingredient).where(Ingredient.name == "薑"))
    assert client.put(f"/api/v1/dishes/{safe['id']}/recipe", headers=headers, json={
        "items": [{"ingredient_id": str(ginger.id), "quantity": "1", "unit": "kg", "loss_rate": "0"}],
    }).status_code == 200
    statements = []
    process_engine = db_session.get_bind()
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record)
    try:
        search = client.post("/api/v1/postpartum/replacement-candidates/search", headers=headers, json={
            "target_date": TARGET_DATE, "postpartum_meal": "lunch", "items": [item],
            "page": 1, "page_size": 20,
        })
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert search.status_code == 200, search.text
    by_id = {row["dish"]["id"]: row for row in search.json()["items"]}
    assert by_id[item["original_dish_id"]]["status"] == "conflict"
    assert by_id[dishes[1]["id"]]["status"] == "conflict"
    assert by_id[dishes[2]["id"]]["status"] == "insufficient_recipe_data"
    assert by_id[safe["id"]]["status"] == "no_known_conflict"
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 12  # auth + fixed conflict preload + candidate page/count/recipe

    rejected = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "replacement_dish_id": item["original_dish_id"], "items": [item],
    })
    assert rejected.status_code == 422
    ingredient_rejected = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "replacement_dish_id": dishes[1]["id"], "items": [item],
    })
    assert ingredient_rejected.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(PostpartumReplacementGroup)) == 0

    created = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "replacement_dish_id": dishes[2]["id"], "items": [item], "note": "人工確認配方",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["candidate_status"] == "insufficient_recipe_data"
    assert body["review_needed"] is True and body["status"] == "replaced"
    statements = []
    event.listen(process_engine, "before_cursor_execute", record)
    try:
        listing = client.get(
            f"/api/v1/postpartum/conflict-handlings?target_date={TARGET_DATE}&postpartum_meal=lunch",
            headers=headers,
        )
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert listing.status_code == 200
    assert "replaced" in {row["status"] for row in listing.json()["conflict_items"]}
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 14  # fixed daily read; independent of group/item counts
    duplicate = client.post("/api/v1/postpartum/conflict-acknowledgements", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch", "item": item,
    })
    assert duplicate.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "postpartum_replacement_group_create",
    )) == 1

    removed = client.post(
        f"/api/v1/postpartum/replacement-groups/{body['id']}/cancel", headers=headers,
    )
    assert removed.status_code == 204
    assert db_session.scalar(select(func.count()).select_from(PostpartumReplacementGroup)) == 0
    assert db_session.scalar(select(func.count()).select_from(PostpartumConflictHandling)) == 0


def test_manual_acknowledgement_can_be_cancelled(client, db_session):
    headers, _, _, _, _ = configure_conflict_scenario(client, db_session)
    item = _conflict(client, headers)
    response = client.post("/api/v1/postpartum/conflict-acknowledgements", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch", "item": item,
        "note": "已人工確認",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "manually_acknowledged"
    listing = client.get(
        f"/api/v1/postpartum/conflict-handlings?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    ).json()
    assert len(listing["manual_acknowledgements"]) == 1
    assert client.post(
        f"/api/v1/postpartum/conflict-acknowledgements/{body['id']}/cancel", headers=headers,
    ).status_code == 204
    assert db_session.scalar(select(func.count()).select_from(PostpartumConflictHandling)) == 0


def test_item_can_move_between_groups_and_stale_original_requires_reconfirmation(
    client, db_session, monkeypatch,
):
    headers, _, _, _, dishes = configure_conflict_scenario(client, db_session)
    conflict_response = client.get(
        f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    ).json()
    menu_dishes = {item["menu_dish_id"]: item for item in conflict_response["menu_dishes"]}
    conflicts = [item for item in conflict_response["case_dish_results"] if item["outcome"] == "conflict"]
    items = [{
        "case_id": item["case_id"], "original_menu_dish_id": item["menu_dish_id"],
        "original_dish_id": menu_dishes[item["menu_dish_id"]]["dish"]["id"],
    } for item in conflicts]
    groups = []
    for item in items:
        response = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
            "target_date": TARGET_DATE, "postpartum_meal": "lunch",
            "replacement_dish_id": dishes[2]["id"], "items": [item],
        })
        assert response.status_code == 201, response.text
        groups.append(response.json())

    lock_modes = []
    original_conflict_handlings = PostpartumRepository.conflict_handlings

    def tracked_conflict_handlings(repository, target_date, postpartum_meal, for_update=False):
        lock_modes.append(for_update)
        return original_conflict_handlings(
            repository, target_date, postpartum_meal, for_update=for_update,
        )

    monkeypatch.setattr(PostpartumRepository, "conflict_handlings", tracked_conflict_handlings)
    blocked = client.put(f"/api/v1/postpartum/replacement-groups/{groups[0]['id']}", headers=headers, json={
        "replacement_dish_id": dishes[2]["id"], "items": items,
    })
    assert blocked.status_code == 409
    assert True in lock_modes
    moved = client.put(f"/api/v1/postpartum/replacement-groups/{groups[0]['id']}", headers=headers, json={
        "replacement_dish_id": dishes[2]["id"], "items": items, "reassign_items": True,
    })
    assert moved.status_code == 200, moved.text
    assert len(moved.json()["items"]) == 2
    listing = client.get(
        f"/api/v1/postpartum/conflict-handlings?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    ).json()
    assert [item["id"] for item in listing["replacement_groups"]] == [groups[0]["id"]]

    db_session.execute(delete(MenuDish).where(MenuDish.id == items[0]["original_menu_dish_id"]))
    db_session.commit()
    revalidated = client.post(
        f"/api/v1/postpartum/replacement-groups/{groups[0]['id']}/revalidate", headers=headers,
    )
    assert revalidated.status_code == 200, revalidated.text
    assert revalidated.json()["status"] == "requires_reconfirmation"
    stale_item = next(item for item in revalidated.json()["items"] if (
        item["original_menu_dish_id"] == items[0]["original_menu_dish_id"]
    ))
    assert stale_item["status"] == "requires_reconfirmation"
    assert stale_item["warnings"][0]["code"] == "ORIGINAL_MENU_DISH_STALE"


def test_group_accepts_multiple_cases_and_different_original_dishes_but_rejects_wrong_slot(client, db_session):
    headers, first_case, _, _, dishes = configure_conflict_scenario(client, db_session)
    second_case = create_case(client, headers, "P-004", status="active")
    group_ids = list(db_session.scalars(select(PostpartumRestrictionGroup.id)))
    assigned = client.put(
        f"/api/v1/postpartum/cases/{second_case['id']}/restriction-groups", headers=headers,
        json={"restriction_group_ids": [str(item) for item in group_ids]},
    )
    assert assigned.status_code == 200, assigned.text
    evaluation = client.get(
        f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    ).json()
    menu_dishes = {item["menu_dish_id"]: item for item in evaluation["menu_dishes"]}
    conflicts = [item for item in evaluation["case_dish_results"] if item["outcome"] == "conflict"]
    first = next(item for item in conflicts if item["case_id"] == first_case["id"])
    second = next(item for item in conflicts if (
        item["case_id"] == second_case["id"] and item["menu_dish_id"] != first["menu_dish_id"]
    ))
    items = [{
        "case_id": item["case_id"], "original_menu_dish_id": item["menu_dish_id"],
        "original_dish_id": menu_dishes[item["menu_dish_id"]]["dish"]["id"],
    } for item in (first, second)]
    wrong_slot = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": "2026-09-11", "postpartum_meal": "lunch",
        "replacement_dish_id": dishes[2]["id"], "items": items,
    })
    assert wrong_slot.status_code == 422
    created = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "replacement_dish_id": dishes[2]["id"], "items": items,
    })
    assert created.status_code == 201, created.text
    assert {item["case_id"] for item in created.json()["items"]} == {
        first_case["id"], second_case["id"],
    }


def test_update_reconfirms_same_menu_dish_after_its_dish_identity_changes(client, db_session):
    headers, _, _, _, dishes = configure_conflict_scenario(client, db_session)
    original_item = _conflict(client, headers)
    assert original_item["original_dish_id"] == dishes[0]["id"]
    created = client.post("/api/v1/postpartum/replacement-groups", headers=headers, json={
        "target_date": TARGET_DATE, "postpartum_meal": "lunch",
        "replacement_dish_id": dishes[2]["id"], "items": [original_item],
    })
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]

    # Preserve MenuDish UUID X while changing its referenced Dish A -> Dish B.
    db_session.execute(delete(MenuDish).where(
        MenuDish.dish_id == dishes[1]["id"],
        MenuDish.id != original_item["original_menu_dish_id"],
    ))
    db_session.execute(update(MenuDish).where(
        MenuDish.id == original_item["original_menu_dish_id"],
    ).values(dish_id=dishes[1]["id"]))
    db_session.commit()

    stale = client.get(
        f"/api/v1/postpartum/conflict-handlings?target_date={TARGET_DATE}&postpartum_meal=lunch",
        headers=headers,
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["replacement_groups"][0]["status"] == "requires_reconfirmation"

    current_item = {
        **original_item,
        "original_dish_id": dishes[1]["id"],
    }
    refreshed = client.put(
        f"/api/v1/postpartum/replacement-groups/{group_id}", headers=headers,
        json={"replacement_dish_id": dishes[2]["id"], "items": [current_item]},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["status"] == "replaced"
    assert refreshed.json()["items"][0]["status"] == "replaced"
    db_session.expire_all()
    persisted = db_session.scalar(select(PostpartumConflictHandling).where(
        PostpartumConflictHandling.original_menu_dish_id == original_item["original_menu_dish_id"],
    ))
    assert str(persisted.original_dish_id) == dishes[1]["id"]

    mismatch = client.put(
        f"/api/v1/postpartum/replacement-groups/{group_id}", headers=headers,
        json={"replacement_dish_id": dishes[2]["id"], "items": [original_item]},
    )
    assert mismatch.status_code == 422
    db_session.expire_all()
    persisted = db_session.scalar(select(PostpartumConflictHandling).where(
        PostpartumConflictHandling.id == persisted.id,
    ))
    assert str(persisted.original_dish_id) == dishes[1]["id"]
