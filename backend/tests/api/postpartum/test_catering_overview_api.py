from zipfile import ZipFile
from io import BytesIO

from sqlalchemy import event

from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(
        username="catering_admin", password=PASSWORD, display_name="Catering Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def payload(number, room, **overrides):
    value = {
        "case_number": number, "name": f"個案{number}", "current_room": room,
        "delivery_type": "vaginal", "delivery_date": "2026-09-01",
        "service_start_date": "2026-09-12", "service_start_meal": "breakfast",
        "service_end_date": "2026-09-12", "service_end_meal": "evening_snack",
        "status": "ended", "preparation_mode": "herbal", "service_note": "少鹽",
    }
    value.update(overrides)
    return value


def test_catering_overview_api_eligibility_groups_and_docx(client, db_session):
    headers = auth(client, db_session)
    ten = client.post("/api/v1/postpartum/cases", headers=headers, json=payload("010", "10")).json()
    two = client.post("/api/v1/postpartum/cases", headers=headers, json=payload("002", "2", service_start_meal="lunch")).json()
    paused = client.post("/api/v1/postpartum/cases", headers=headers, json=payload("003", "3")).json()
    client.post(f"/api/v1/postpartum/cases/{paused['id']}/pauses", headers=headers, json={
        "start_date": "2026-09-12", "start_meal": "breakfast",
        "end_date": "2026-09-12", "end_meal": "evening_snack", "note": "全天停餐",
    })
    group = client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={
        "name": "不牛", "color": "#aa0000", "notes": None,
    }).json()
    assert client.put(f"/api/v1/postpartum/cases/{two['id']}/restriction-groups", headers=headers, json={"restriction_group_ids": [group["id"]]}).status_code == 200
    client.post(f"/api/v1/postpartum/restriction-groups/{group['id']}/deactivate", headers=headers)

    response = client.get("/api/v1/postpartum/catering-overview?target_date=2026-09-12", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    assert [item["current_room"] for item in data["items"]] == ["2", "10"]
    assert data["items"][0]["restriction_groups"] == [{"id": group["id"], "name": "不牛", "color": "#AA0000", "is_active": False}]
    assert data["items"][0]["service_meals"][0] == {"meal": "lunch", "label": "午餐"}
    assert data["items"][0]["service_start_date"] == "2026-09-12"
    assert data["items"][0]["service_start_meal_label"] == "午餐"
    assert data["items"][0]["service_end_date"] == "2026-09-12"
    assert data["items"][0]["service_end_meal_label"] == "晚點"
    assert data["items"][1]["case_id"] == ten["id"]

    document = client.get("/api/v1/postpartum/catering-overview.docx?target_date=2026-09-12", headers=headers)
    assert document.status_code == 200
    assert document.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(document.content) > 1000
    with ZipFile(BytesIO(document.content)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "月子餐個案供餐總覽表" not in xml
    assert "停伙：" not in xml
    for text in ("2026 年 09 月 12 日", "星期六", "供餐總床數：2 床", "不牛", "個案002", "少鹽"):
        assert text in xml


def test_catering_overview_requires_auth_and_has_empty_state(client, db_session):
    assert client.get("/api/v1/postpartum/catering-overview?target_date=2026-09-12").status_code == 401
    headers = auth(client, db_session)
    assert client.get("/api/v1/postpartum/catering-overview", headers=headers).status_code == 422
    assert client.get("/api/v1/postpartum/catering-overview?target_date=not-a-date", headers=headers).status_code == 422
    assert client.get("/api/v1/postpartum/catering-overview?target_date=2026-09-12", headers=headers).json()["items"] == []
    document = client.get("/api/v1/postpartum/catering-overview.docx?target_date=2026-09-12", headers=headers)
    assert document.status_code == 200 and len(document.content) > 1000
    assert "本日沒有符合供餐條件的月子餐個案" in ZipFile(BytesIO(document.content)).read("word/document.xml").decode("utf-8")


def test_catering_overview_has_fixed_read_only_query_budget(client, db_session):
    headers = auth(client, db_session)
    client.post("/api/v1/postpartum/cases", headers=headers, json=payload("099", "99"))
    statements = []
    process_engine = db_session.get_bind()

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip().upper())

    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/v1/postpartum/catering-overview?target_date=2026-09-12", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert sum(statement.startswith("SELECT") for statement in statements) <= 4
    assert not any(statement.startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
