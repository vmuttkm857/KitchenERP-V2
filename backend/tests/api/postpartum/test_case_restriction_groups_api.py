import uuid

from sqlalchemy import event, select

from app.domains.audit.models import AuditLog
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(
        username="case_restriction_admin", password=PASSWORD,
        display_name="Case Restriction Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={
        "username": user.username, "password": PASSWORD,
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user


def create_case(client, headers, number="CR-001"):
    response = client.post("/api/v1/postpartum/cases", headers=headers, json={
        "case_number": number, "name": "王小姐", "current_room": "503",
        "delivery_type": "vaginal", "delivery_date": "2026-09-08",
        "service_start_date": "2026-09-09", "service_start_meal": "breakfast",
        "service_end_date": None, "service_end_meal": None, "status": "active",
        "preparation_mode": "no_herbal", "service_note": None,
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_group(client, headers, name, color="#AA2200"):
    response = client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={
        "name": name, "color": color, "notes": None,
    })
    assert response.status_code == 201, response.text
    return response.json()


def replace(client, headers, case_id, group_ids):
    return client.put(f"/api/v1/postpartum/cases/{case_id}/restriction-groups", headers=headers, json={
        "restriction_group_ids": group_ids,
    })


def test_assign_replace_clear_dedupe_and_case_responses(client, db_session):
    headers, _ = auth(client, db_session)
    case = create_case(client, headers)
    beef = create_group(client, headers, "不牛", "#AA2200")
    fish = create_group(client, headers, "不魚", "#0066AA")

    assigned = replace(client, headers, case["id"], [fish["id"], beef["id"], beef["id"]])
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["case_id"] == case["id"]
    assert [item["name"] for item in assigned.json()["restriction_groups"]] == ["不牛", "不魚"]

    detail = client.get(f"/api/v1/postpartum/cases/{case['id']}", headers=headers).json()
    assert [item["id"] for item in detail["restriction_groups"]] == [beef["id"], fish["id"]]
    listing = client.get("/api/v1/postpartum/cases", headers=headers).json()["items"]
    listed = next(item for item in listing if item["id"] == case["id"])
    assert [item["name"] for item in listed["restriction_groups"]] == ["不牛", "不魚"]

    replaced = replace(client, headers, case["id"], [fish["id"]])
    assert [item["id"] for item in replaced.json()["restriction_groups"]] == [fish["id"]]
    cleared = replace(client, headers, case["id"], [])
    assert cleared.status_code == 200 and cleared.json()["restriction_groups"] == []


def test_invalid_group_rolls_back_and_auth_is_required(client, db_session):
    headers, _ = auth(client, db_session)
    case = create_case(client, headers, "CR-002")
    group = create_group(client, headers, "不內臟")
    assert replace(client, headers, case["id"], [group["id"]]).status_code == 200
    assert client.put(f"/api/v1/postpartum/cases/{case['id']}/restriction-groups", json={
        "restriction_group_ids": [],
    }).status_code == 401

    invalid = replace(client, headers, case["id"], [str(uuid.uuid4())])
    assert invalid.status_code == 422
    detail = client.get(f"/api/v1/postpartum/cases/{case['id']}", headers=headers).json()
    assert [item["id"] for item in detail["restriction_groups"]] == [group["id"]]


def test_inactive_existing_group_can_remain_or_be_removed_but_not_added(client, db_session):
    headers, _ = auth(client, db_session)
    case = create_case(client, headers, "CR-003")
    existing = create_group(client, headers, "不奶")
    newly_inactive = create_group(client, headers, "退奶飲食")
    assert replace(client, headers, case["id"], [existing["id"]]).status_code == 200
    assert client.post(f"/api/v1/postpartum/restriction-groups/{existing['id']}/deactivate", headers=headers).status_code == 200
    assert client.post(f"/api/v1/postpartum/restriction-groups/{newly_inactive['id']}/deactivate", headers=headers).status_code == 200

    retained = replace(client, headers, case["id"], [existing["id"]])
    assert retained.status_code == 200
    assert retained.json()["restriction_groups"] == [{
        "id": existing["id"], "name": "不奶", "color": "#AA2200", "is_active": False,
    }]
    detail = client.get(f"/api/v1/postpartum/cases/{case['id']}", headers=headers).json()
    listing = client.get("/api/v1/postpartum/cases", headers=headers).json()["items"][0]
    assert detail["restriction_groups"][0]["is_active"] is False
    assert listing["restriction_groups"][0]["is_active"] is False

    rejected = replace(client, headers, case["id"], [existing["id"], newly_inactive["id"]])
    assert rejected.status_code == 422
    assert [item["id"] for item in client.get(f"/api/v1/postpartum/cases/{case['id']}", headers=headers).json()["restriction_groups"]] == [existing["id"]]
    assert replace(client, headers, case["id"], []).status_code == 200
    assert replace(client, headers, case["id"], [existing["id"]]).status_code == 422


def test_assignment_audit_and_case_list_fixed_query_budget(client, db_session):
    headers, user = auth(client, db_session)
    case = create_case(client, headers, "CR-004")
    groups = [create_group(client, headers, name) for name in ("不牛", "不魚", "不內臟")]
    requested = [groups[2]["id"], groups[0]["id"], groups[1]["id"]]
    assert replace(client, headers, case["id"], requested).status_code == 200
    audit = db_session.scalar(select(AuditLog).where(
        AuditLog.action == "postpartum_case_restriction_groups_replace",
        AuditLog.entity_id == case["id"],
    ).order_by(AuditLog.created_at.desc()))
    assert audit is not None and audit.actor_user_id == user.id
    assert audit.before_data == {"restriction_group_ids": []}
    assert audit.after_data == {"restriction_group_ids": sorted(requested)}

    statements = []
    process_engine = db_session.get_bind()
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/v1/postpartum/cases?page=1&page_size=25", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 4
