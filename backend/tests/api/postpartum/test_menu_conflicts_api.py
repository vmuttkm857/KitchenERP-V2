import uuid

from sqlalchemy import event, func, select

from app.domains.audit.models import AuditLog
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"
TARGET_DATE = "2026-09-10"


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(
        username=f"conflict-{uuid.uuid4().hex[:8]}", password=PASSWORD,
        display_name="Conflict Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={
        "username": user.username, "password": PASSWORD,
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_menu(client, headers, name, start=TARGET_DATE, end=TARGET_DATE):
    menu = client.post("/api/v1/menus", headers=headers, json={
        "name": name, "start_date": start, "end_date": end,
    }).json()
    breakfast = client.post(f"/api/v1/menus/{menu['id']}/meal-types", headers=headers, json={
        "name": "ERP 早餐", "sort_order": 1,
    }).json()
    lunch = client.post(f"/api/v1/menus/{menu['id']}/meal-types", headers=headers, json={
        "name": "ERP 午餐", "sort_order": 2,
    }).json()
    return menu, breakfast, lunch


def create_source(client, headers, menu, mappings):
    response = client.post("/api/v1/postpartum/menu-sources", headers=headers, json={
        "menu_id": menu["id"], "mappings": mappings,
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_masters(client, headers):
    ingredient_category = client.post("/api/v1/categories/ingredient", headers=headers, json={
        "name": "衝突食材", "sort_order": 1,
    }).json()
    dish_category = client.post("/api/v1/categories/dish", headers=headers, json={
        "name": "衝突菜色", "sort_order": 1,
    }).json()
    ingredients = []
    for index, name in enumerate(("牛肉", "薑"), 1):
        ingredients.append(client.post("/api/v1/ingredients", headers=headers, json={
            "code": f"CI-{index}", "name": name, "category_id": ingredient_category["id"],
            "unit": "kg", "current_price": "1",
        }).json())
    dishes = []
    for index, name in enumerate(("直接禁忌菜", "牛肉料理", "無配方菜"), 1):
        dishes.append(client.post("/api/v1/dishes", headers=headers, json={
            "code": f"CD-{index}", "name": name, "category_id": dish_category["id"],
        }).json())
    assert client.put(f"/api/v1/dishes/{dishes[0]['id']}/recipe", headers=headers, json={
        "items": [{"ingredient_id": ingredients[1]["id"], "quantity": "1", "unit": "kg", "loss_rate": "0"}],
    }).status_code == 200
    assert client.put(f"/api/v1/dishes/{dishes[1]['id']}/recipe", headers=headers, json={
        "items": [{"ingredient_id": ingredients[0]["id"], "quantity": "1", "unit": "kg", "loss_rate": "0"}],
    }).status_code == 200
    return ingredients, dishes


def schedule(client, headers, menu, lunch, dishes):
    response = client.put(f"/api/v1/menus/{menu['id']}/editor", headers=headers, json={
        "slots": [{
            "menu_date": TARGET_DATE, "menu_meal_type_id": lunch["id"],
            "dishes": [
                {"dish_id": dish["id"], "diner_count": 10, "sort_order": index}
                for index, dish in enumerate(dishes, 1)
            ],
        }],
    })
    assert response.status_code == 200, response.text


def create_case(client, headers, number, *, active=True, status="ended"):
    response = client.post("/api/v1/postpartum/cases", headers=headers, json={
        "case_number": number, "name": f"個案 {number}", "current_room": number,
        "delivery_type": "vaginal", "delivery_date": "2026-09-01",
        "service_start_date": TARGET_DATE, "service_start_meal": "breakfast",
        "service_end_date": TARGET_DATE, "service_end_meal": "dinner",
        "status": status, "preparation_mode": "no_herbal", "service_note": None,
    })
    assert response.status_code == 201, response.text
    value = response.json()
    if not active:
        client.post(f"/api/v1/postpartum/cases/{value['id']}/deactivate", headers=headers)
    return value


def create_group(client, headers, name, notes=None):
    response = client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={
        "name": name, "color": "#AA2200", "notes": notes,
    })
    assert response.status_code == 201, response.text
    return response.json()


def configure_conflict_scenario(client, db_session):
    headers = auth(client, db_session)
    ingredients, dishes = create_masters(client, headers)
    menu, _, lunch = create_menu(client, headers, "衝突檢查菜單")
    schedule(client, headers, menu, lunch, dishes)
    create_source(client, headers, menu, [{
        "postpartum_meal": "lunch", "menu_meal_type_id": lunch["id"],
    }])
    eligible = create_case(client, headers, "P-001", status="ended")
    paused = create_case(client, headers, "P-002", status="active")
    inactive = create_case(client, headers, "P-003", active=False, status="active")
    client.post(f"/api/v1/postpartum/cases/{paused['id']}/pauses", headers=headers, json={
        "start_date": TARGET_DATE, "start_meal": "lunch",
        "end_date": TARGET_DATE, "end_meal": "lunch", "note": "停餐",
    })
    direct = create_group(client, headers, "直接菜色")
    ingredient = create_group(client, headers, "不牛")
    note_only = create_group(client, headers, "人工禁忌", "請人工判斷")
    client.put(f"/api/v1/postpartum/restriction-groups/{direct['id']}/associations", headers=headers, json={
        "ingredient_ids": [], "dish_ids": [dishes[0]["id"]],
    })
    client.put(f"/api/v1/postpartum/restriction-groups/{ingredient['id']}/associations", headers=headers, json={
        "ingredient_ids": [ingredients[0]["id"]], "dish_ids": [],
    })
    client.put(f"/api/v1/postpartum/cases/{eligible['id']}/restriction-groups", headers=headers, json={
        "restriction_group_ids": [direct["id"], ingredient["id"], note_only["id"]],
    })
    return headers, eligible, paused, inactive, dishes


def test_conflicts_exact_matching_eligibility_partial_coverage_and_read_only(client, db_session):
    headers, eligible, paused, inactive, dishes = configure_conflict_scenario(client, db_session)
    audit_before = db_session.scalar(select(func.count()).select_from(AuditLog))
    statements = []
    process_engine = db_session.get_bind()
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get(
            f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch",
            headers=headers,
        )
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evaluation_status"] == "partial" and body["evaluation_performed"] is True
    assert body["source_resolution"]["status"] == "available"
    assert body["mapping_resolution"]["status"] == "mapped"
    assert [item["dish"]["name"] for item in body["menu_dishes"]] == [
        "直接禁忌菜", "牛肉料理", "無配方菜",
    ]
    assert [item["id"] for item in body["eligible_cases"]] == [eligible["id"]]
    assert paused["id"] not in {item["id"] for item in body["eligible_cases"]}
    assert inactive["id"] not in {item["id"] for item in body["eligible_cases"]}
    by_dish = {item["menu_dish_id"]: item for item in body["case_dish_results"]}
    menu_dish_ids = [item["menu_dish_id"] for item in body["menu_dishes"]]
    assert [reason["type"] for reason in by_dish[menu_dish_ids[0]]["reasons"]] == ["direct_dish"]
    assert [reason["type"] for reason in by_dish[menu_dish_ids[1]]["reasons"]] == ["ingredient"]
    assert by_dish[menu_dish_ids[2]]["outcome"] == "unknown"
    assert body["menu_dishes"][2]["ingredient_coverage"] == "partial"
    assert "RESTRICTION_GROUP_NOTE_ONLY" in {
        item["code"] for item in body["eligible_cases"][0]["warnings"]
    }
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 9  # auth plus eight fixed batch queries, including both association tables
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == audit_before


def test_unavailable_source_unmapped_inactive_and_ambiguous_states(client, db_session):
    headers = auth(client, db_session)
    path = f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch"
    missing = client.get(path, headers=headers).json()
    assert missing["evaluation_status"] == "unavailable"
    assert missing["warnings"][0]["code"] == "SOURCE_NOT_CONFIGURED"

    first, breakfast, _ = create_menu(client, headers, "第一份")
    create_source(client, headers, first, [{
        "postpartum_meal": "breakfast", "menu_meal_type_id": breakfast["id"],
    }])
    unmapped = client.get(path, headers=headers).json()
    assert unmapped["mapping_resolution"]["status"] == "not_mapped"
    assert unmapped["evaluation_performed"] is False and unmapped["warnings"] == []

    client.post(f"/api/v1/menus/{first['id']}/deactivate", headers=headers)
    inactive = client.get(path, headers=headers).json()
    assert inactive["source_resolution"]["status"] == "inactive"
    assert inactive["warnings"][0]["code"] == "MENU_INACTIVE"
    client.post(f"/api/v1/menus/{first['id']}/reactivate", headers=headers)

    second, second_breakfast, _ = create_menu(
        client, headers, "第二份", "2026-09-11", "2026-09-11",
    )
    create_source(client, headers, second, [{
        "postpartum_meal": "breakfast", "menu_meal_type_id": second_breakfast["id"],
    }])
    assert client.patch(f"/api/v1/menus/{second['id']}", headers=headers, json={
        "start_date": TARGET_DATE,
    }).status_code == 200
    ambiguous = client.get(path, headers=headers).json()
    assert ambiguous["source_resolution"]["status"] == "ambiguous"
    assert len(ambiguous["source_resolution"]["candidates"]) == 2
    assert ambiguous["warnings"][0]["code"] == "SOURCE_AMBIGUOUS"


def test_complete_no_conflict_and_query_count_is_fixed(client, db_session):
    headers = auth(client, db_session)
    ingredients, dishes = create_masters(client, headers)
    menu, _, lunch = create_menu(client, headers, "完整菜單")
    schedule(client, headers, menu, lunch, dishes[:2])
    create_source(client, headers, menu, [{
        "postpartum_meal": "lunch", "menu_meal_type_id": lunch["id"],
    }])
    create_case(client, headers, "P-100", status="pending")
    path = f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch"
    statements = []
    process_engine = db_session.get_bind()
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get(path, headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evaluation_status"] == "complete"
    assert {item["outcome"] for item in body["case_dish_results"]} == {"no_conflict"}
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 9  # auth plus eight fixed domain metadata/association/recipe queries


def test_missing_menu_day_and_inactive_mapped_meal_are_unavailable(client, db_session):
    headers = auth(client, db_session)
    menu, _, lunch = create_menu(client, headers, "尚未排菜")
    create_source(client, headers, menu, [{
        "postpartum_meal": "lunch", "menu_meal_type_id": lunch["id"],
    }])
    path = f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch"
    missing_day = client.get(path, headers=headers).json()
    assert missing_day["evaluation_status"] == "unavailable"
    assert missing_day["warnings"][0]["code"] == "MENU_DAY_NOT_CONFIGURED"
    client.post(f"/api/v1/menus/{menu['id']}/meal-types/{lunch['id']}/deactivate", headers=headers)
    inactive_meal = client.get(path, headers=headers).json()
    assert inactive_meal["mapping_resolution"]["status"] == "inactive"
    assert inactive_meal["warnings"][0]["code"] == "MEAL_TYPE_INACTIVE"


def test_auth_and_invalid_meal_are_rejected(client, db_session):
    headers = auth(client, db_session)
    path = f"/api/v1/postpartum/menu-conflicts?target_date={TARGET_DATE}&postpartum_meal=lunch"
    assert client.get(path).status_code == 401
    assert client.get(path.replace("lunch", "brunch"), headers=headers).status_code == 422


def test_daily_conflicts_return_six_canonical_meals_and_case_details(client, db_session):
    headers, eligible, _, _, _ = configure_conflict_scenario(client, db_session)
    statements = []
    process_engine = db_session.get_bind()

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get(
            f"/api/v1/postpartum/menu-conflicts/daily?target_date={TARGET_DATE}",
            headers=headers,
        )
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    body = response.json()
    expected_meals = [
        "breakfast", "morning_snack", "lunch",
        "afternoon_snack", "dinner", "evening_snack",
    ]
    assert [item["postpartum_meal"] for item in body["meals"]] == expected_meals
    assert [item["postpartum_meal"] for item in body["summaries"]] == expected_meals
    lunch = body["meals"][2]
    assert [item["id"] for item in lunch["eligible_cases"]] == [eligible["id"]]
    assert body["summaries"][2]["status"] == "conflict"
    assert body["summaries"][2]["conflict_case_count"] == 1
    assert body["summaries"][2]["conflict_count"] == 2
    assert body["summaries"][0]["status"] == "unmapped"
    assert body["conflict_case_count"] == 1 and body["conflict_count"] == 2
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 9  # auth plus the same eight fixed preload queries used by one meal


def test_weekly_conflicts_are_monday_to_sunday_with_7_by_6_fixed_query_budget(client, db_session):
    headers, _, _, _, _ = configure_conflict_scenario(client, db_session)
    statements = []
    process_engine = db_session.get_bind()

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get(
            f"/api/v1/postpartum/menu-conflicts/weekly?anchor_date={TARGET_DATE}",
            headers=headers,
        )
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["week_start"] == "2026-09-07"
    assert body["week_end"] == "2026-09-13"
    assert len(body["days"]) == 7
    assert all(len(day["meals"]) == 6 for day in body["days"])
    assert [item["postpartum_meal"] for item in body["days"][0]["meals"]] == [
        "breakfast", "morning_snack", "lunch",
        "afternoon_snack", "dinner", "evening_snack",
    ]
    target_day = next(item for item in body["days"] if item["target_date"] == TARGET_DATE)
    assert target_day["meals"][2]["status"] == "conflict"
    assert body["days"][0]["meals"][0]["status"] == "unavailable"
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 9  # query count does not grow to 42 evaluations


def test_daily_summaries_cover_missing_ambiguous_and_no_eligible_cases(client, db_session):
    headers = auth(client, db_session)
    path = f"/api/v1/postpartum/menu-conflicts/daily?target_date={TARGET_DATE}"
    missing = client.get(path, headers=headers).json()
    assert {item["status"] for item in missing["summaries"]} == {"unavailable"}
    assert {item["source_status"] for item in missing["summaries"]} == {"not_configured"}

    ingredients, dishes = create_masters(client, headers)
    first, breakfast, lunch = create_menu(client, headers, "第一份日總覽")
    schedule(client, headers, first, lunch, dishes[:2])
    create_source(client, headers, first, [{
        "postpartum_meal": "lunch", "menu_meal_type_id": lunch["id"],
    }])
    no_cases = client.get(path, headers=headers).json()
    assert no_cases["meals"][2]["eligible_cases"] == []
    assert no_cases["summaries"][2]["status"] == "complete"
    assert no_cases["summaries"][2]["eligible_case_count"] == 0

    second, second_breakfast, _ = create_menu(
        client, headers, "第二份日總覽", "2026-09-11", "2026-09-11",
    )
    create_source(client, headers, second, [{
        "postpartum_meal": "breakfast", "menu_meal_type_id": second_breakfast["id"],
    }])
    assert client.patch(f"/api/v1/menus/{second['id']}", headers=headers, json={
        "start_date": TARGET_DATE,
    }).status_code == 200
    ambiguous = client.get(path, headers=headers).json()
    assert {item["status"] for item in ambiguous["summaries"]} == {"unavailable"}
    assert {item["source_status"] for item in ambiguous["summaries"]} == {"ambiguous"}
