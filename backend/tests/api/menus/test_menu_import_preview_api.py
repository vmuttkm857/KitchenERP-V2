import uuid
from datetime import date, timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.dishes.models import Dish
from app.domains.menus.models import Menu, MenuDish
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD = "correct horse battery staple"


def auth(client: TestClient, session: Session):
    user = UserService(session).create_user(CreateUserCommand(
        username="menu_import_admin", password=PASSWORD, display_name="Menu Import Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={
        "username": user.username, "password": PASSWORD,
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_xlsx(rows, *, start=date(2026, 9, 28)):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "標準週菜單"
    sheet.append(["餐別", "菜單欄位", *[start + timedelta(days=value) for value in range(7)]])
    for row in rows:
        sheet.append(list(row))
    output = BytesIO(); workbook.save(output)
    return output.getvalue()


def create_category(client, headers):
    response = client.post("/api/v1/categories/dish", headers=headers, json={"name": "匯入測試"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_dish(client, headers, category_id, code, name, *, active=True):
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


def preview(client, headers, payload):
    return client.post(
        "/api/v1/menu-imports/preview",
        headers=headers,
        files={"file": ("週菜單.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_preview_matches_deterministically_and_is_read_only(client, db_session):
    headers = auth(client, db_session)
    category_id = create_category(client, headers)
    exact = create_dish(client, headers, category_id, "I-1", "精確菜")
    nfkc = create_dish(client, headers, category_id, "I-2", "Ａ菜")
    whitespace = create_dish(client, headers, category_id, "I-3", "空 白 菜")
    inactive = create_dish(client, headers, category_id, "I-4", "停用菜", active=False)
    payload = make_xlsx([
        ["早餐", "主菜", "精確菜", "A菜", "  空   白   菜  ", "精確", "停用菜", "不存在", None],
    ])
    menu_count = db_session.scalar(select(func.count()).select_from(Menu))
    menu_dish_count = db_session.scalar(select(func.count()).select_from(MenuDish))

    response = preview(client, headers, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [line["status"] for line in body["lines"]] == [
        "MATCHED", "MATCHED", "MATCHED", "UNMATCHED", "INACTIVE_MATCH", "UNMATCHED",
    ]
    assert [line["dish"]["id"] if line["dish"] else None for line in body["lines"][:3]] == [
        exact["id"], nfkc["id"], whitespace["id"],
    ]
    assert body["lines"][4]["dish"]["id"] == inactive["id"]
    assert body["lines"][2]["original_import_name"] == "  空   白   菜  "
    assert all(line["diner_count"] == 1 for line in body["lines"])
    assert body["summary"] == {
        "date_count": 7, "meal_count": 1, "column_count": 1, "dish_count": 6,
        "matched_count": 3, "review_required_count": 3,
        "duplicate_conflict_count": 0, "excluded_count": 0,
    }
    second = preview(client, headers, payload).json()
    assert [line["line_key"] for line in second["lines"]] == [line["line_key"] for line in body["lines"]]
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Menu)) == menu_count
    assert db_session.scalar(select(func.count()).select_from(MenuDish)) == menu_dish_count
    assert db_session.get(Dish, uuid.UUID(exact["id"])) is not None


def test_normalization_ambiguity_never_auto_matches(client, db_session):
    headers = auth(client, db_session)
    category_id = create_category(client, headers)
    create_dish(client, headers, category_id, "AMB-1", "ＡＢ菜")
    create_dish(client, headers, category_id, "AMB-2", "AB菜")

    response = preview(client, headers, make_xlsx([
        ["早餐", "主菜", "ＡＢ菜", None, None, None, None, None, None],
    ]))

    assert response.status_code == 200, response.text
    line = response.json()["lines"][0]
    assert line["status"] == "AMBIGUOUS"
    assert line["dish"] is None
    assert line["review_required"] is True


def test_overlap_is_reported_without_modifying_existing_menu(client, db_session):
    headers = auth(client, db_session)
    menu_category = client.post("/api/v1/categories/menu", headers=headers, json={"name": "一般菜單"}).json()
    menu_response = client.post("/api/v1/menus", headers=headers, json={
        "name": "既有跨月菜單", "start_date": "2026-09-30", "end_date": "2026-10-06",
        "category_id": menu_category["id"],
    })
    assert menu_response.status_code == 201, menu_response.text
    before = menu_response.json()

    response = preview(client, headers, make_xlsx([
        ["早餐", "主菜", "未知菜", None, None, None, None, None, None],
    ]))

    assert response.status_code == 200, response.text
    overlaps = response.json()["overlapping_menus"]
    assert [(item["id"], item["name"]) for item in overlaps] == [(before["id"], "既有跨月菜單")]
    after = client.get(f"/api/v1/menus/{before['id']}", headers=headers)
    assert after.status_code == 200
    assert after.json()["name"] == before["name"]
    assert db_session.scalar(select(func.count()).select_from(MenuDish)) == 0


def test_preview_validation_error_is_domain_specific_and_route_requires_auth(client, db_session):
    headers = auth(client, db_session)

    unauthenticated = client.post(
        "/api/v1/menu-imports/preview", files={"file": ("menu.xlsx", b"invalid", "application/octet-stream")},
    )
    assert unauthenticated.status_code == 401
    invalid = preview(client, headers, b"invalid")
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "MENU_IMPORT_INVALID"
    assert "traceback" not in invalid.text.lower()


def test_formula_in_dish_area_is_a_fatal_preview_error(client, db_session):
    headers = auth(client, db_session)
    response = preview(client, headers, make_xlsx([
        ["早餐", "主菜", "=CONCAT(\"菜\",\"A\")", None, None, None, None, None, None],
    ]))

    assert response.status_code == 200, response.text
    assert any("菜色不可使用公式" in item for item in response.json()["fatal_errors"])
    assert response.json()["summary"]["dish_count"] == 0
