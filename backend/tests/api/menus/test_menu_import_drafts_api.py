import uuid
from datetime import date, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.audit.models import AuditLog
from app.domains.dishes.models import Dish
from app.domains.menu_imports.models import MenuImportBatch, MenuImportLine
from app.domains.menu_imports.repository import MenuImportRepository
from app.domains.menu_imports.service import MenuImportService
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType, MenuMealTypeColumn
from app.domains.menus.service import MenuService
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService
from app.core.config import settings

PASSWORD = "correct horse battery staple"


def test_delete_is_allowed_by_cross_origin_preflight(client):
    response = client.options(
        "/api/v1/menu-imports/00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": settings.cors_origins[0],
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def auth(client: TestClient, session: Session, username="import_draft_admin", role="admin"):
    user = UserService(session).create_user(CreateUserCommand(
        username=username, password=PASSWORD, display_name="Import Draft Admin", role=role,
    ))
    token = client.post("/api/v1/auth/login", json={
        "username": username, "password": PASSWORD,
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user


def make_xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "標準菜單"
    sheet.append(["餐別", "菜單欄位", *[date(2026, 10, 5) + timedelta(days=value) for value in range(7)]])
    for row in rows:
        sheet.append(list(row))
    output = BytesIO(); workbook.save(output)
    return output.getvalue()


def dish_category(client, headers):
    response = client.post("/api/v1/categories/dish", headers=headers, json={"name": "匯入草稿"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def dish(client, headers, category_id, code, name, active=True):
    response = client.post("/api/v1/dishes", headers=headers, json={
        "code": code, "name": name, "category_id": category_id,
    })
    assert response.status_code == 201, response.text
    value = response.json()
    if not active:
        response = client.post(f"/api/v1/dishes/{value['id']}/deactivate", headers=headers)
        assert response.status_code == 200, response.text
        value = response.json()
    return value


def upload(client, headers, path, payload, data=None):
    return client.post(
        path,
        headers=headers,
        data=data or {},
        files={"file": ("C:/fake/path/週菜單.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def preview(client, headers, payload):
    response = upload(client, headers, "/api/v1/menu-imports/preview", payload)
    assert response.status_code == 200, response.text
    return response.json()


def create_draft(client, headers, payload, source_hash):
    return upload(client, headers, "/api/v1/menu-imports", payload, {"expected_source_hash": source_hash})


def test_create_persists_all_match_states_and_get_list_refetch(client, db_session):
    headers, user = auth(client, db_session)
    category_id = dish_category(client, headers)
    matched = dish(client, headers, category_id, "D-1", "精確菜")
    inactive = dish(client, headers, category_id, "D-2", "停用菜", active=False)
    dish(client, headers, category_id, "D-3", "ＡＢ菜")
    dish(client, headers, category_id, "D-4", "AB菜")
    payload = make_xlsx([
        ["早餐", "主菜", "精確菜", "不存在", "停用菜", "ＡＢ菜", None, None, None],
        ["早餐", "副菜", None, None, None, None, "精確菜", None, None],
    ])
    parsed = preview(client, headers, payload)

    response = create_draft(client, headers, payload, parsed["source_hash"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "週菜單.xlsx"
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["summary"] == parsed["summary"]
    assert body["layout"] == parsed["layout"]
    assert [line["resolution_status"] for line in body["lines"]] == [
        "MATCHED", "UNMATCHED", "INACTIVE_MATCH", "AMBIGUOUS", "MATCHED",
    ]
    assert body["lines"][0]["dish"]["id"] == matched["id"]
    assert body["lines"][2]["dish"] is None
    assert body["lines"][2]["resolution_status"] == "INACTIVE_MATCH"
    assert all(line["diner_count"] == 1 for line in body["lines"])
    assert body["lines"][1]["original_import_name"] == "不存在"
    assert body["lines"][1]["source_row"] == 2
    assert body["lines"][1]["source_column"] == 4
    assert body["lines"][4]["meal_sort_order"] == 1
    assert body["lines"][4]["column_sort_order"] == 2
    assert [line["line_key"] for line in body["lines"]] == [line["line_key"] for line in parsed["lines"]]
    assert body["created_by"] == str(user.id)

    first_refetch = client.get(f"/api/v1/menu-imports/{body['id']}", headers=headers)
    second_refetch = client.get(f"/api/v1/menu-imports/{body['id']}", headers=headers)
    assert first_refetch.status_code == second_refetch.status_code == 200
    assert first_refetch.json() == second_refetch.json()
    assert first_refetch.json()["layout"] == parsed["layout"]
    listing = client.get("/api/v1/menu-imports", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] == 1
    assert listing.json()["items"][0]["id"] == body["id"]
    actions = set(db_session.scalars(select(AuditLog.action)))
    assert "menu_import_draft_create" in actions

    hard_delete = client.post(
        f"/api/v1/dishes/{matched['id']}/hard-delete", headers=headers, json={"password": PASSWORD},
    )
    assert hard_delete.status_code == 204, hard_delete.text
    after_dish_delete = client.get(f"/api/v1/menu-imports/{body['id']}", headers=headers)
    assert after_dish_delete.status_code == 200
    assert after_dish_delete.json()["lines"][0]["dish"] is None
    assert after_dish_delete.json()["lines"][0]["resolution_status"] == "MATCHED"


def test_resolve_only_one_line_recounts_until_ready_and_preserves_original(client, db_session):
    headers, _ = auth(client, db_session)
    category_id = dish_category(client, headers)
    selected = dish(client, headers, category_id, "R-1", "人工對應菜")
    payload = make_xlsx([
        ["早餐", "主菜", "原始錯字一", "原始錯字二", None, None, None, None, None],
    ])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()
    first, second = created["lines"]
    assert created["summary"]["review_required_count"] == 2

    response = client.patch(
        f"/api/v1/menu-imports/{created['id']}/lines/{first['id']}",
        headers=headers,
        json={"dish_id": selected["id"]},
    )

    assert response.status_code == 200, response.text
    after_one = response.json()
    by_id = {line["id"]: line for line in after_one["lines"]}
    assert after_one["summary"]["review_required_count"] == 1
    assert after_one["status"] == "REVIEW_REQUIRED"
    assert by_id[first["id"]]["original_import_name"] == "原始錯字一"
    assert by_id[first["id"]]["dish"]["id"] == selected["id"]
    assert by_id[first["id"]]["resolution_status"] == "MANUALLY_RESOLVED"
    assert by_id[first["id"]]["review_required"] is False
    assert by_id[first["id"]]["resolved_at"] is not None
    assert by_id[first["id"]]["resolved_by"] is not None
    assert by_id[second["id"]]["review_required"] is True

    final = client.patch(
        f"/api/v1/menu-imports/{created['id']}/lines/{second['id']}",
        headers=headers,
        json={"dish_id": selected["id"]},
    )
    assert final.status_code == 200
    assert final.json()["summary"]["review_required_count"] == 0
    assert final.json()["status"] == "READY"
    refetched = client.get(f"/api/v1/menu-imports/{created['id']}", headers=headers).json()
    assert refetched["status"] == "READY"
    assert refetched["summary"] == final.json()["summary"]
    assert [(line["id"], line["original_import_name"], line["dish"]["id"], line["resolution_status"])
            for line in refetched["lines"]] == [
        (line["id"], line["original_import_name"], line["dish"]["id"], line["resolution_status"])
        for line in final.json()["lines"]
    ]
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "menu_import_line_resolve",
    )) == 2


def test_resolve_rejects_missing_inactive_and_wrong_batch_line(client, db_session):
    headers, _ = auth(client, db_session)
    category_id = dish_category(client, headers)
    active = dish(client, headers, category_id, "V-1", "可選菜")
    inactive = dish(client, headers, category_id, "V-2", "不可選菜", active=False)
    first_payload = make_xlsx([["早餐", "主菜", "錯字一", None, None, None, None, None, None]])
    second_payload = make_xlsx([["早餐", "主菜", "錯字二", None, None, None, None, None, None]])
    first_preview = preview(client, headers, first_payload)
    second_preview = preview(client, headers, second_payload)
    first = create_draft(client, headers, first_payload, first_preview["source_hash"]).json()
    second = create_draft(client, headers, second_payload, second_preview["source_hash"]).json()
    line_id = first["lines"][0]["id"]

    missing = client.patch(
        f"/api/v1/menu-imports/{first['id']}/lines/{line_id}", headers=headers,
        json={"dish_id": str(uuid.uuid4())},
    )
    inactive_response = client.patch(
        f"/api/v1/menu-imports/{first['id']}/lines/{line_id}", headers=headers,
        json={"dish_id": inactive["id"]},
    )
    wrong_batch = client.patch(
        f"/api/v1/menu-imports/{second['id']}/lines/{line_id}", headers=headers,
        json={"dish_id": active["id"]},
    )

    assert missing.status_code == inactive_response.status_code == 422
    assert wrong_batch.status_code == 404
    unchanged = client.get(f"/api/v1/menu-imports/{first['id']}", headers=headers).json()
    assert unchanged["summary"]["review_required_count"] == 1
    assert unchanged["lines"][0]["dish"] is None


def test_hash_fatal_duplicate_and_transaction_failure_leave_no_partial_batch(client, db_session, monkeypatch):
    headers, user = auth(client, db_session)
    payload = make_xlsx([["早餐", "主菜", "未知菜", None, None, None, None, None, None]])
    parsed = preview(client, headers, payload)

    mismatch = create_draft(client, headers, payload, "0" * 64)
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "SOURCE_HASH_MISMATCH"
    assert db_session.scalar(select(func.count()).select_from(MenuImportBatch)) == 0

    fatal_payload = make_xlsx([["早餐", "主菜", "=1+1", None, None, None, None, None, None]])
    fatal_preview = preview(client, headers, fatal_payload)
    fatal = create_draft(client, headers, fatal_payload, fatal_preview["source_hash"])
    assert fatal.status_code == 422
    assert fatal.json()["detail"]["code"] == "MENU_IMPORT_FATAL"
    assert db_session.scalar(select(func.count()).select_from(MenuImportBatch)) == 0

    service = MenuImportService(db_session)
    original_add = service.repository.add
    calls = 0

    def fail_on_line(value):
        nonlocal calls
        calls += 1
        original_add(value)
        if calls == 2:
            raise RuntimeError("simulated line insert failure")

    monkeypatch.setattr(service.repository, "add", fail_on_line)
    with pytest.raises(RuntimeError, match="simulated"):
        service.create_draft(payload, "menu.xlsx", None, parsed["source_hash"], user.id)
    assert db_session.scalar(select(func.count()).select_from(MenuImportBatch)) == 0
    assert db_session.scalar(select(func.count()).select_from(MenuImportLine)) == 0

    created = create_draft(client, headers, payload, parsed["source_hash"])
    assert created.status_code == 201, created.text
    duplicate = create_draft(client, headers, payload, parsed["source_hash"])
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "MENU_IMPORT_DRAFT_EXISTS", "existing_batch_id": created.json()["id"],
    }
    assert db_session.scalar(select(func.count()).select_from(MenuImportBatch)) == 1


def test_delete_cascades_only_staging_and_all_authenticated_users_follow_role_based_access(client, db_session):
    headers, _ = auth(client, db_session)
    payload = make_xlsx([["早餐", "主菜", "未知菜", None, None, None, None, None, None]])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()
    menu_count = db_session.scalar(select(func.count()).select_from(Menu))
    menu_dish_count = db_session.scalar(select(func.count()).select_from(MenuDish))

    other_headers, _ = auth(client, db_session, username="second_import_user", role="user")
    assert client.get(f"/api/v1/menu-imports/{created['id']}", headers=other_headers).status_code == 200
    assert client.get(f"/api/v1/menu-imports/{created['id']}").status_code == 401
    response = client.delete(f"/api/v1/menu-imports/{created['id']}", headers=headers)

    assert response.status_code == 204, response.text
    assert client.get(f"/api/v1/menu-imports/{created['id']}", headers=headers).status_code == 404
    assert db_session.scalar(select(func.count()).select_from(MenuImportLine)) == 0
    assert db_session.scalar(select(func.count()).select_from(MenuImportBatch)) == 0
    assert db_session.scalar(select(func.count()).select_from(Menu)) == menu_count
    assert db_session.scalar(select(func.count()).select_from(MenuDish)) == menu_dish_count
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "menu_import_draft_delete",
    )) == 1


def test_duplicate_can_be_recreated_after_draft_deletion(client, db_session):
    headers, _ = auth(client, db_session)
    payload = make_xlsx([["早餐", "主菜", "未知菜", None, None, None, None, None, None]])
    parsed = preview(client, headers, payload)
    first = create_draft(client, headers, payload, parsed["source_hash"]).json()
    assert client.delete(f"/api/v1/menu-imports/{first['id']}", headers=headers).status_code == 204
    second = create_draft(client, headers, payload, parsed["source_hash"])
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_duplicate_lines_exclude_restore_and_audit_are_backend_authoritative(client, db_session):
    headers, user = auth(client, db_session, username="import_duplicate_admin")
    category_id = dish_category(client, headers)
    matched = dish(client, headers, category_id, "DUP-1", "重複雞腿")
    payload = make_xlsx([
        ["午餐", "便當主菜", "重複雞腿", None, None, None, None, None, None],
        ["午餐", "第二主菜", "重複雞腿", None, None, None, None, None, None],
    ])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()
    first, second = created["lines"]

    assert created["status"] == "REVIEW_REQUIRED"
    assert created["summary"]["duplicate_conflict_count"] == 2
    assert all(line["duplicate_conflict"] for line in created["lines"])
    assert created["can_finalize"] is False

    excluded = client.post(
        f"/api/v1/menu-imports/{created['id']}/lines/{second['id']}/exclude", headers=headers,
    )
    assert excluded.status_code == 200, excluded.text
    body = excluded.json()
    excluded_line = next(line for line in body["lines"] if line["id"] == second["id"])
    assert excluded_line["resolution_status"] == "EXCLUDED"
    assert excluded_line["dish"] is None
    assert excluded_line["review_required"] is False
    assert excluded_line["duplicate_conflict"] is False
    assert excluded_line["original_import_name"] == "重複雞腿"
    assert excluded_line["excluded_at"] is not None
    assert excluded_line["excluded_by"] == str(user.id)
    assert body["summary"]["excluded_count"] == 1
    assert body["summary"]["duplicate_conflict_count"] == 0
    assert body["status"] == "READY"
    assert body["can_finalize"] is True
    assert db_session.get(Dish, uuid.UUID(matched["id"])) is not None
    assert db_session.get(MenuImportLine, uuid.UUID(second["id"])) is not None

    restored = client.post(
        f"/api/v1/menu-imports/{created['id']}/lines/{second['id']}/restore", headers=headers,
    )
    assert restored.status_code == 200, restored.text
    body = restored.json()
    restored_line = next(line for line in body["lines"] if line["id"] == second["id"])
    assert restored_line["resolution_status"] == "MATCHED"
    assert restored_line["dish"]["id"] == matched["id"]
    assert restored_line["excluded_at"] is None
    assert restored_line["excluded_by"] is None
    assert body["summary"]["duplicate_conflict_count"] == 2
    assert body["summary"]["excluded_count"] == 0
    assert body["status"] == "REVIEW_REQUIRED"
    actions = set(db_session.scalars(select(AuditLog.action)))
    assert {"menu_import_line_exclude", "menu_import_line_restore"}.issubset(actions)


def test_manual_changes_are_repeatable_preserve_original_and_create_or_clear_duplicates(client, db_session):
    headers, _ = auth(client, db_session, username="import_reassign_admin")
    category_id = dish_category(client, headers)
    dish_a = dish(client, headers, category_id, "REP-A", "原配菜")
    dish_b = dish(client, headers, category_id, "REP-B", "另一配菜")
    dish_c = dish(client, headers, category_id, "REP-C", "第三配菜")
    payload = make_xlsx([
        ["晚餐", "副菜1", "原配菜", None, None, None, None, None, None],
        ["晚餐", "副菜2", "另一配菜", None, None, None, None, None, None],
    ])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()
    first, second = created["lines"]

    duplicate = client.patch(
        f"/api/v1/menu-imports/{created['id']}/lines/{second['id']}", headers=headers,
        json={"dish_id": dish_a["id"]},
    ).json()
    changed = next(line for line in duplicate["lines"] if line["id"] == second["id"])
    assert changed["resolution_status"] == "MANUALLY_RESOLVED"
    assert changed["original_import_name"] == "另一配菜"
    assert duplicate["summary"]["duplicate_conflict_count"] == 2
    assert duplicate["status"] == "REVIEW_REQUIRED"

    cleared = client.patch(
        f"/api/v1/menu-imports/{created['id']}/lines/{second['id']}", headers=headers,
        json={"dish_id": dish_c["id"]},
    ).json()
    changed_again = next(line for line in cleared["lines"] if line["id"] == second["id"])
    assert changed_again["resolution_status"] == "MANUALLY_RESOLVED"
    assert changed_again["original_import_name"] == "另一配菜"
    assert changed_again["dish"]["id"] == dish_c["id"]
    assert cleared["summary"]["duplicate_conflict_count"] == 0
    assert cleared["status"] == "READY"
    assert cleared["can_finalize"] is True
    assert first["dish"]["id"] == dish_a["id"]
    assert dish_b["id"] != dish_c["id"]
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "menu_import_line_resolve",
    )) == 2


@pytest.mark.parametrize("kind", ["unmatched", "ambiguous", "inactive"])
def test_restore_reapplies_deterministic_matching_states(client, db_session, kind):
    headers, _ = auth(client, db_session, username=f"restore_{kind}_admin")
    category_id = dish_category(client, headers)
    if kind == "unmatched":
        imported_name, expected = "完全不存在", "UNMATCHED"
    elif kind == "ambiguous":
        dish(client, headers, category_id, "AMB-1", "ＡＢ菜")
        dish(client, headers, category_id, "AMB-2", "AB菜")
        imported_name, expected = "ＡＢ菜", "AMBIGUOUS"
    else:
        dish(client, headers, category_id, "INA-1", "停用恢復菜", active=False)
        imported_name, expected = "停用恢復菜", "INACTIVE_MATCH"
    payload = make_xlsx([["早餐", "主菜", imported_name, None, None, None, None, None, None]])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()
    line = created["lines"][0]
    assert client.post(f"/api/v1/menu-imports/{created['id']}/lines/{line['id']}/exclude", headers=headers).status_code == 200
    restored = client.post(f"/api/v1/menu-imports/{created['id']}/lines/{line['id']}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    value = restored.json()["lines"][0]
    assert value["resolution_status"] == expected
    assert value["review_required"] is True
    assert value["dish"] is None


def test_duplicate_identity_is_scoped_by_date_and_meal_and_finalize_checks_active_dishes(client, db_session):
    headers, _ = auth(client, db_session, username="import_scope_admin")
    category_id = dish_category(client, headers)
    matched = dish(client, headers, category_id, "SCOPE-1", "範圍菜")
    payload = make_xlsx([
        ["早餐", "主菜", "範圍菜", "範圍菜", None, None, None, None, None],
        ["午餐", "主菜", "範圍菜", None, None, None, None, None, None],
    ])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()
    assert created["summary"]["duplicate_conflict_count"] == 0
    assert created["status"] == "READY"
    assert MenuImportService(db_session).can_finalize(uuid.UUID(created["id"])) is True
    response = client.post(f"/api/v1/dishes/{matched['id']}/deactivate", headers=headers)
    assert response.status_code == 200
    assert MenuImportService(db_session).can_finalize(uuid.UUID(created["id"])) is False
    detail = client.get(f"/api/v1/menu-imports/{created['id']}", headers=headers).json()
    assert detail["can_finalize"] is False
    assert "已有對應菜色已停用" in detail["finalize_warnings"]


def test_three_duplicate_lines_count_every_conflicting_line(client, db_session):
    headers, _ = auth(client, db_session, username="import_three_duplicates_admin")
    category_id = dish_category(client, headers)
    dish(client, headers, category_id, "DUP-3", "三筆重複菜")
    payload = make_xlsx([
        ["午餐", "主菜", "三筆重複菜", None, None, None, None, None, None],
        ["午餐", "副菜1", "三筆重複菜", None, None, None, None, None, None],
        ["午餐", "副菜2", "三筆重複菜", None, None, None, None, None, None],
    ])
    parsed = preview(client, headers, payload)
    created = create_draft(client, headers, payload, parsed["source_hash"]).json()

    assert created["summary"]["duplicate_conflict_count"] == 3
    assert [line["duplicate_conflict"] for line in created["lines"]] == [True, True, True]
    assert created["status"] == "REVIEW_REQUIRED"
    assert created["can_finalize"] is False


def test_finalize_builds_a_normal_menu_preserves_layout_and_is_idempotent(client, db_session, monkeypatch):
    headers, user = auth(client, db_session, username="import_finalize_admin")
    category_id = dish_category(client, headers)
    auto = dish(client, headers, category_id, "FIN-A", "自動菜")
    manual = dish(client, headers, category_id, "FIN-M", "最後人工菜")
    excluded_dish = dish(client, headers, category_id, "FIN-X", "排除菜")
    existing = client.post("/api/v1/menus", headers=headers, json={
        "name":"既有重疊菜單","start_date":"2026-10-05","end_date":"2026-10-11",
        "category_id":None,"notes":None,
    }).json()
    existing_meal=client.post(f"/api/v1/menus/{existing['id']}/meal-types",headers=headers,json={"name":"既有早餐","sort_order":1}).json()
    existing_column=client.post(f"/api/v1/menus/{existing['id']}/meal-types/{existing_meal['id']}/columns",headers=headers,json={"name":"既有主菜","sort_order":1}).json()
    existing_saved=client.put(f"/api/v1/menus/{existing['id']}/editor",headers=headers,json={"slots":[{
        "menu_date":"2026-10-05","menu_meal_type_id":existing_meal["id"],"dishes":[{
            "dish_id":auto["id"],"menu_meal_type_column_id":existing_column["id"],
            "diner_count":88,"notes":"既有內容","sort_order":1,
        }],
    }]}).json()
    menu_category=client.post("/api/v1/categories/menu",headers=headers,json={"name":"Excel 匯入分類"}).json()
    payload = make_xlsx([
        ["早餐", "主菜", "自動菜", None, None, None, None, None, None],
        ["早餐", "副菜", "Excel 原始錯字", None, None, None, None, None, None],
        ["早餐", "整週空白欄", None, None, None, None, None, None, None],
        ["午餐", "主菜", "排除菜", None, None, None, None, None, None],
    ])
    parsed=preview(client,headers,payload)
    created=create_draft(client,headers,payload,parsed["source_hash"]).json()
    typo=next(line for line in created["lines"] if line["original_import_name"]=="Excel 原始錯字")
    changed=client.patch(f"/api/v1/menu-imports/{created['id']}/lines/{typo['id']}",headers=headers,json={"dish_id":manual["id"]}).json()
    excluded=next(line for line in changed["lines"] if line["original_import_name"]=="排除菜")
    ready=client.post(f"/api/v1/menu-imports/{created['id']}/lines/{excluded['id']}/exclude",headers=headers).json()
    assert ready["status"]=="READY"

    lock_calls=[]
    original_batch=MenuImportRepository.batch
    def record_batch_lock(repository,batch_id,*,for_update=False):
        lock_calls.append(for_update)
        return original_batch(repository,batch_id,for_update=for_update)
    monkeypatch.setattr(MenuImportRepository,"batch",record_batch_lock)
    response=client.post(f"/api/v1/menu-imports/{created['id']}/finalize",headers=headers,json={
        "name":"Excel 正式菜單","category_id":menu_category["id"],"notes":"匯入完成",
    })
    assert response.status_code==200,response.text
    assert True in lock_calls
    result=response.json();menu_id=result["finalized_menu_id"]
    assert result["already_finalized"] is False
    assert result["menu"]["name"]=="Excel 正式菜單"
    assert result["menu"]["category_id"]==menu_category["id"]
    assert result["menu"]["notes"]=="匯入完成"
    editor=client.get(f"/api/v1/menus/{menu_id}/editor",headers=headers)
    assert editor.status_code==200,editor.text
    value=editor.json()
    assert value["dates"]==[(date(2026,10,5)+timedelta(days=i)).isoformat() for i in range(7)]
    assert [(meal["name"],meal["sort_order"]) for meal in value["meal_types"]]==[("早餐",1),("午餐",2)]
    columns={(next(meal["name"] for meal in value["meal_types"] if meal["id"]==column["menu_meal_type_id"]),column["name"],column["sort_order"]) for column in value["meal_type_columns"]}
    assert ("早餐","整週空白欄",3) in columns
    dishes=[detail for slot in value["slots"] for detail in slot["dishes"]]
    assert {item["dish_id"] for item in dishes}=={auto["id"],manual["id"]}
    assert excluded_dish["id"] not in {item["dish_id"] for item in dishes}
    assert all(item["diner_count"]==1 for item in dishes)
    assert all(item["notes"] is None for item in dishes)
    column_names={column["id"]:column["name"] for column in value["meal_type_columns"]}
    assert {item["dish_id"]:column_names[item["menu_meal_type_column_id"]] for item in dishes}=={
        auto["id"]:"主菜",manual["id"]:"副菜",
    }
    assert len(value["slots"])==14
    assert db_session.get(Menu,uuid.UUID(existing["id"])).name=="既有重疊菜單"
    assert client.get(f"/api/v1/menus/{existing['id']}/editor",headers=headers).json()==existing_saved
    assert db_session.scalar(select(func.count()).select_from(Menu))==2

    retry=client.post(f"/api/v1/menu-imports/{created['id']}/finalize",headers=headers,json={
        "name":"不應建立第二份","category_id":None,"notes":None,
    })
    assert retry.status_code==200
    assert retry.json()["already_finalized"] is True
    assert retry.json()["finalized_menu_id"]==menu_id
    assert db_session.scalar(select(func.count()).select_from(Menu))==2
    detail=client.get(f"/api/v1/menu-imports/{created['id']}",headers=headers).json()
    assert detail["status"]=="FINALIZED"
    assert detail["finalized_menu_id"]==menu_id
    assert detail["finalized_by"]==str(user.id)
    assert detail["finalized_at"] is not None
    assert detail["finalized_menu"]["name"]=="Excel 正式菜單"
    assert client.get("/api/v1/menu-imports",headers=headers).json()["pagination"]["total"]==0
    assert client.patch(f"/api/v1/menu-imports/{created['id']}/lines/{typo['id']}",headers=headers,json={"dish_id":auto["id"]}).status_code==409
    assert client.post(f"/api/v1/menu-imports/{created['id']}/lines/{typo['id']}/exclude",headers=headers).status_code==409
    assert client.post(f"/api/v1/menu-imports/{created['id']}/lines/{excluded['id']}/restore",headers=headers).status_code==409
    assert client.delete(f"/api/v1/menu-imports/{created['id']}",headers=headers).status_code==409
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="menu_import_finalize"))==1


def test_finalize_rejects_unready_inactive_and_slot_collision_without_partial_menu(client, db_session, monkeypatch):
    headers,_=auth(client,db_session,username="import_finalize_reject_admin")
    category_id=dish_category(client,headers)
    first=dish(client,headers,category_id,"REJ-A","有效菜一")
    second=dish(client,headers,category_id,"REJ-B","有效菜二")
    unresolved_payload=make_xlsx([["早餐","主菜","不存在",None,None,None,None,None,None]])
    parsed=preview(client,headers,unresolved_payload)
    unresolved=create_draft(client,headers,unresolved_payload,parsed["source_hash"]).json()
    rejected=client.post(f"/api/v1/menu-imports/{unresolved['id']}/finalize",headers=headers,json={"name":"不可建立"})
    assert rejected.status_code==409
    assert rejected.json()["detail"]["code"]=="MENU_IMPORT_NOT_READY"

    missing=dish(client,headers,category_id,"REJ-X","稍後刪除菜")
    missing_payload=make_xlsx([["早餐","主菜","稍後刪除菜",None,None,None,None,None,None]])
    parsed=preview(client,headers,missing_payload);missing_ready=create_draft(client,headers,missing_payload,parsed["source_hash"]).json()
    assert client.post(f"/api/v1/dishes/{missing['id']}/hard-delete",headers=headers,json={"password":PASSWORD}).status_code==204
    missing_response=client.post(f"/api/v1/menu-imports/{missing_ready['id']}/finalize",headers=headers,json={"name":"刪除後不可建立"})
    assert missing_response.status_code==409
    assert missing_response.json()["detail"]["code"]=="MENU_IMPORT_NOT_READY"
    assert db_session.scalar(select(func.count()).select_from(Menu).where(Menu.name=="刪除後不可建立"))==0

    duplicate_payload=make_xlsx([
        ["午餐","主菜","有效菜一",None,None,None,None,None,None],
        ["午餐","副菜","有效菜一",None,None,None,None,None,None],
    ])
    parsed=preview(client,headers,duplicate_payload);duplicate=create_draft(client,headers,duplicate_payload,parsed["source_hash"]).json()
    assert duplicate["summary"]["duplicate_conflict_count"]==2
    duplicate_response=client.post(f"/api/v1/menu-imports/{duplicate['id']}/finalize",headers=headers,json={"name":"重複不可建立"})
    assert duplicate_response.status_code==409
    assert db_session.scalar(select(func.count()).select_from(Menu).where(Menu.name=="重複不可建立"))==0

    payload=make_xlsx([
        ["午餐","主菜","有效菜一",None,None,None,None,None,None],
        ["午餐","副菜","有效菜二",None,None,None,None,None,None],
    ])
    parsed=preview(client,headers,payload);ready=create_draft(client,headers,payload,parsed["source_hash"]).json()
    client.post(f"/api/v1/dishes/{first['id']}/deactivate",headers=headers)
    inactive=client.post(f"/api/v1/menu-imports/{ready['id']}/finalize",headers=headers,json={"name":"停用不可建立"})
    assert inactive.status_code==409
    assert db_session.scalar(select(func.count()).select_from(Menu).where(Menu.name=="停用不可建立"))==0
    client.post(f"/api/v1/dishes/{first['id']}/reactivate",headers=headers)
    lines={line["original_import_name"]:line for line in ready["lines"]}
    db_session.get(MenuImportLine,uuid.UUID(lines["有效菜二"]["id"])).column_name="主菜"
    db_session.get(MenuImportLine,uuid.UUID(lines["有效菜二"]["id"])).column_sort_order=1
    db_session.commit()
    collision=client.post(f"/api/v1/menu-imports/{ready['id']}/finalize",headers=headers,json={"name":"欄位衝突"})
    assert collision.status_code==422
    assert db_session.scalar(select(func.count()).select_from(Menu).where(Menu.name=="欄位衝突"))==0

    db_session.get(MenuImportLine,uuid.UUID(lines["有效菜二"]["id"])).column_name="副菜"
    db_session.get(MenuImportLine,uuid.UUID(lines["有效菜二"]["id"])).column_sort_order=2
    db_session.commit()
    original=MenuService.stage_imported_menu
    def fail_after_staging(service,*args,**kwargs):
        original(service,*args,**kwargs)
        raise RuntimeError("simulated finalize failure")
    monkeypatch.setattr(MenuService,"stage_imported_menu",fail_after_staging)
    with pytest.raises(RuntimeError,match="simulated finalize failure"):
        MenuImportService(db_session).finalize(uuid.UUID(ready["id"]),"交易回滾",None,None,uuid.UUID(ready["created_by"]))
    assert db_session.scalar(select(func.count()).select_from(Menu).where(Menu.name=="交易回滾"))==0
    assert db_session.get(MenuImportBatch,uuid.UUID(ready["id"])).status=="READY"
