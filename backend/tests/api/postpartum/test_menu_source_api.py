import uuid

import pytest
from sqlalchemy import func, select

from app.domains.audit.models import AuditLog
from app.domains.postpartum.models import PostpartumMenuSource
from app.domains.postpartum.schemas import MenuSourceReplace
from app.domains.postpartum.service import PostpartumService
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD = "correct horse battery staple"
MEALS = ("breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner", "evening_snack")


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(
        username=f"source-{uuid.uuid4().hex[:8]}", password=PASSWORD,
        display_name="Menu Source Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user


def menu_with_meals(client, headers, name="月子餐菜單", start="2026-09-01", end="2026-09-07"):
    menu = client.post("/api/v1/menus", headers=headers, json={
        "name": name, "start_date": start, "end_date": end,
    }).json()
    meal_types = [client.post(f"/api/v1/menus/{menu['id']}/meal-types", headers=headers, json={
        "name": f"餐別 {index}", "sort_order": index,
    }).json() for index in range(1, 7)]
    return menu, meal_types


def source_payload(menu, meal_types, count=6):
    return {"menu_id": menu["id"], "mappings": [
        {"postpartum_meal": meal, "menu_meal_type_id": meal_type["id"]}
        for meal, meal_type in zip(MEALS[:count], meal_types[:count], strict=True)
    ]}


@pytest.mark.parametrize("count", [1, 3, 6])
def test_create_optional_mapping_counts_and_list_detail(client, db_session, count):
    headers, _ = auth(client, db_session)
    menu, meal_types = menu_with_meals(client, headers)
    saved = client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(menu, meal_types, count))
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["configured"] is True and body["usable"] is True
    assert len(body["mappings"]) == count
    assert len(body["meal_statuses"]) == 6
    assert sum(item["mapped"] for item in body["meal_statuses"]) == count
    assert body["warnings"] == []
    listed = client.get("/api/v1/postpartum/menu-sources", headers=headers).json()["items"]
    assert [item["id"] for item in listed] == [body["id"]]
    assert client.get(f"/api/v1/postpartum/menu-sources/{body['id']}", headers=headers).json() == body


def test_zero_duplicate_meal_and_duplicate_type_are_rejected(client, db_session):
    headers, _ = auth(client, db_session)
    menu, meal_types = menu_with_meals(client, headers)
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json={"menu_id": menu["id"], "mappings": []}).status_code == 422
    duplicate_meal = source_payload(menu, meal_types, 2)
    duplicate_meal["mappings"][1]["postpartum_meal"] = "breakfast"
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=duplicate_meal).status_code == 422
    duplicate_type = source_payload(menu, meal_types, 2)
    duplicate_type["mappings"][1]["menu_meal_type_id"] = duplicate_type["mappings"][0]["menu_meal_type_id"]
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=duplicate_type).status_code == 422


def test_wrong_menu_inactive_targets_and_duplicate_menu_are_rejected(client, db_session):
    headers, _ = auth(client, db_session)
    menu, meal_types = menu_with_meals(client, headers, "第一份")
    other, other_meals = menu_with_meals(client, headers, "第二份", "2026-09-08", "2026-09-14")
    wrong = source_payload(menu, meal_types, 1)
    wrong["mappings"][0]["menu_meal_type_id"] = other_meals[0]["id"]
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=wrong).status_code == 422
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(menu, meal_types, 1)).status_code == 201
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(menu, meal_types, 1)).status_code == 422
    assert db_session.scalar(select(func.count()).select_from(PostpartumMenuSource)) == 1
    client.post(f"/api/v1/menus/{other['id']}/deactivate", headers=headers)
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(other, other_meals, 1)).status_code == 422
    third, third_meals = menu_with_meals(client, headers, "第三份", "2026-09-15", "2026-09-21")
    client.post(f"/api/v1/menus/{third['id']}/meal-types/{third_meals[0]['id']}/deactivate", headers=headers)
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(third, third_meals, 1)).status_code == 422


def test_overlap_rejected_but_adjacent_inclusive_ranges_allowed(client, db_session):
    headers, _ = auth(client, db_session)
    first, first_meals = menu_with_meals(client, headers, "本週", "2026-09-01", "2026-09-07")
    overlap, overlap_meals = menu_with_meals(client, headers, "重疊", "2026-09-07", "2026-09-13")
    adjacent, adjacent_meals = menu_with_meals(client, headers, "相鄰", "2026-09-08", "2026-09-14")
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(first, first_meals, 1)).status_code == 201
    assert client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(overlap, overlap_meals, 1)).status_code == 422
    adjacent_response = client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(adjacent, adjacent_meals, 1))
    assert adjacent_response.status_code == 201, adjacent_response.text


def test_later_overlap_and_inactive_targets_are_returned_with_warnings(client, db_session):
    headers, _ = auth(client, db_session)
    first, first_meals = menu_with_meals(client, headers, "本週", "2026-09-01", "2026-09-07")
    second, second_meals = menu_with_meals(client, headers, "下週", "2026-09-08", "2026-09-14")
    first_source = client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(first, first_meals, 2)).json()
    client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(second, second_meals, 1))
    changed = client.patch(f"/api/v1/menus/{second['id']}", headers=headers, json={"start_date": "2026-09-07"})
    assert changed.status_code == 200, changed.text
    client.post(f"/api/v1/menus/{first['id']}/deactivate", headers=headers)
    client.post(f"/api/v1/menus/{first['id']}/meal-types/{first_meals[1]['id']}/deactivate", headers=headers)
    body = client.get(f"/api/v1/postpartum/menu-sources/{first_source['id']}", headers=headers).json()
    assert {item["code"] for item in body["warnings"]} == {"MENU_INACTIVE", "MEAL_TYPE_INACTIVE", "SOURCE_DATE_OVERLAP"}
    listed = client.get("/api/v1/postpartum/menu-sources", headers=headers).json()["items"]
    assert all("SOURCE_DATE_OVERLAP" in {warning["code"] for warning in item["warnings"]} for item in listed)


def test_list_date_filter_returns_month_overlap_in_deterministic_order(client, db_session):
    headers, _ = auth(client, db_session)
    ranges = [
        ("跨入九月", "2026-08-31", "2026-09-06"),
        ("九月中旬", "2026-09-07", "2026-09-13"),
        ("跨出九月", "2026-09-28", "2026-10-04"),
        ("十一月", "2026-11-01", "2026-11-07"),
    ]
    created = []
    for name, start, end in ranges:
        menu, meal_types = menu_with_meals(client, headers, name, start, end)
        response = client.post(
            "/api/v1/postpartum/menu-sources", headers=headers,
            json=source_payload(menu, meal_types, 1),
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    response = client.get(
        "/api/v1/postpartum/menu-sources?from_date=2026-09-01&to_date=2026-09-30",
        headers=headers,
    )
    assert response.status_code == 200
    assert [item["menu"]["name"] for item in response.json()["items"]] == [
        "跨入九月", "九月中旬", "跨出九月",
    ]
    assert client.get(
        "/api/v1/postpartum/menu-sources?from_date=2026-10-05&to_date=2026-10-31",
        headers=headers,
    ).json()["items"] == []
    assert client.get(
        "/api/v1/postpartum/menu-sources?from_date=2026-10-31&to_date=2026-10-01",
        headers=headers,
    ).status_code == 422


def test_filtered_list_keeps_inactive_and_later_overlap_warnings(client, db_session):
    headers, _ = auth(client, db_session)
    first, first_meals = menu_with_meals(client, headers, "九月一", "2026-09-01", "2026-09-07")
    second, second_meals = menu_with_meals(client, headers, "九月二", "2026-09-08", "2026-09-14")
    client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(first, first_meals, 1))
    client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(second, second_meals, 1))
    client.patch(f"/api/v1/menus/{second['id']}", headers=headers, json={"start_date": "2026-09-07"})
    client.post(f"/api/v1/menus/{first['id']}/deactivate", headers=headers)
    items = client.get(
        "/api/v1/postpartum/menu-sources?from_date=2026-09-01&to_date=2026-09-30",
        headers=headers,
    ).json()["items"]
    first_warnings = {warning["code"] for warning in items[0]["warnings"]}
    assert first_warnings == {"MENU_INACTIVE", "SOURCE_DATE_OVERLAP"}
    assert {warning["code"] for warning in items[1]["warnings"]} == {"SOURCE_DATE_OVERLAP"}


def test_update_is_atomic_and_audit_contains_before_after(client, db_session, monkeypatch):
    headers, user = auth(client, db_session)
    menu, meal_types = menu_with_meals(client, headers)
    created = client.post("/api/v1/postpartum/menu-sources", headers=headers, json=source_payload(menu, meal_types, 1)).json()
    create_audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "postpartum_menu_source_create").order_by(AuditLog.created_at.desc()))
    assert create_audit.before_data is None and len(create_audit.after_data["mappings"]) == 1
    service = PostpartumService(db_session)
    original = service.menu_source(uuid.UUID(created["id"]))
    def fail_audit(**_kwargs): raise RuntimeError("audit failure")
    monkeypatch.setattr(service.audit, "record", fail_audit)
    with pytest.raises(RuntimeError):
        service.update_menu_source(uuid.UUID(created["id"]), MenuSourceReplace.model_validate(source_payload(menu, meal_types, 3)), user.id)
    db_session.expire_all()
    assert len(PostpartumService(db_session).menu_source(uuid.UUID(created["id"]))["mappings"]) == len(original["mappings"]) == 1
    updated = client.put(f"/api/v1/postpartum/menu-sources/{created['id']}", headers=headers, json=source_payload(menu, meal_types, 3))
    assert updated.status_code == 200 and len(updated.json()["mappings"]) == 3
    update_audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "postpartum_menu_source_update").order_by(AuditLog.created_at.desc()))
    assert len(update_audit.before_data["mappings"]) == 1 and len(update_audit.after_data["mappings"]) == 3
