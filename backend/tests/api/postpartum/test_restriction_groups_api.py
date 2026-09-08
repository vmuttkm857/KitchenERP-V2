import uuid

from sqlalchemy import select

from app.domains.audit.models import AuditLog
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD = "correct horse battery staple"


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(
        username="restriction_admin", password=PASSWORD, display_name="Restriction Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user


def masters(client, headers):
    ingredient_category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "禁忌食材", "sort_order": 1}).json()
    dish_category = client.post("/api/v1/categories/dish", headers=headers, json={"name": "禁忌菜色", "sort_order": 1}).json()
    ingredients = [client.post("/api/v1/ingredients", headers=headers, json={
        "code": f"RI-{index}", "name": name, "category_id": ingredient_category["id"], "unit": "kg", "current_price": "1",
    }).json() for index, name in enumerate(("牛肉片", "牛腱", "牛高湯"), 1)]
    dishes = [client.post("/api/v1/dishes", headers=headers, json={
        "code": f"RD-{index}", "name": name, "category_id": dish_category["id"],
    }).json() for index, name in enumerate(("紅燒牛肉", "牛肉湯", "牛肉燴飯"), 1)]
    return ingredients, dishes


def create_group(client, headers, name="不牛", color="#AA2200", notes="牛肉及牛高湯"):
    response = client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={"name": name, "color": color, "notes": notes})
    assert response.status_code == 201, response.text
    return response.json()


def replace(client, headers, group_id, ingredient_ids, dish_ids):
    return client.put(f"/api/v1/postpartum/restriction-groups/{group_id}/associations", headers=headers, json={
        "ingredient_ids": ingredient_ids, "dish_ids": dish_ids,
    })


def test_group_crud_validation_lifecycle_search_and_pagination(client, db_session):
    headers, user = auth(client, db_session)
    assert client.post("/api/v1/postpartum/restriction-groups", json={"name": "不牛", "color": "#FF0000"}).status_code == 401
    assert client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={"name": "   ", "color": "#FF0000"}).status_code == 422
    assert client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={"name": "不牛", "color": "red"}).status_code == 422

    value = create_group(client, headers, name="  不牛  ", color="#aa2200")
    assert value["name"] == "不牛" and value["color"] == "#AA2200"
    assert value["created_by"] == str(user.id) == value["updated_by"]
    duplicate = client.post("/api/v1/postpartum/restriction-groups", headers=headers, json={"name": " 不牛 ", "color": "#000000"})
    assert duplicate.status_code == 409
    note_only = create_group(client, headers, name="特殊禁忌", color="#0080FF", notes="依個案確認")
    assert note_only["ingredient_count"] == 0 and note_only["dish_count"] == 0
    updated = client.patch(f"/api/v1/postpartum/restriction-groups/{value['id']}", headers=headers, json={"name": "不牛肉", "color": "#00aa55", "notes": None})
    assert updated.status_code == 200
    assert updated.json()["name"] == "不牛肉" and updated.json()["color"] == "#00AA55" and updated.json()["notes"] is None
    assert client.post(f"/api/v1/postpartum/restriction-groups/{value['id']}/deactivate", headers=headers).json()["is_active"] is False
    assert client.get("/api/v1/postpartum/restriction-groups?active=false&search=牛&page=1&page_size=1", headers=headers).json()["pagination"]["total"] == 1
    assert client.post(f"/api/v1/postpartum/restriction-groups/{value['id']}/reactivate", headers=headers).json()["is_active"] is True
    listing = client.get("/api/v1/postpartum/restriction-groups?active=true&page=1&page_size=1", headers=headers).json()
    assert listing["pagination"]["total"] == 2 and len(listing["items"]) == 1


def test_association_replace_counts_duplicates_and_empty_lists(client, db_session):
    headers, _ = auth(client, db_session)
    ingredients, dishes = masters(client, headers)
    group = create_group(client, headers)
    response = replace(client, headers, group["id"], [ingredients[0]["id"], ingredients[0]["id"], ingredients[1]["id"]], [dishes[0]["id"], dishes[1]["id"], dishes[2]["id"]])
    assert response.status_code == 200, response.text
    detail = response.json()
    assert {item["id"] for item in detail["ingredients"]} == {ingredients[0]["id"], ingredients[1]["id"]}
    assert {item["id"] for item in detail["dishes"]} == {item["id"] for item in dishes}
    listing = client.get("/api/v1/postpartum/restriction-groups", headers=headers).json()["items"][0]
    assert listing["ingredient_count"] == 2 and listing["dish_count"] == 3

    replaced = replace(client, headers, group["id"], [ingredients[2]["id"]], [dishes[1]["id"]])
    assert replaced.status_code == 200
    assert [item["id"] for item in replaced.json()["ingredients"]] == [ingredients[2]["id"]]
    assert [item["id"] for item in replaced.json()["dishes"]] == [dishes[1]["id"]]
    emptied = replace(client, headers, group["id"], [], [])
    assert emptied.status_code == 200 and emptied.json()["ingredients"] == [] and emptied.json()["dishes"] == []


def test_invalid_related_ids_roll_back_both_association_sets(client, db_session):
    headers, _ = auth(client, db_session)
    ingredients, dishes = masters(client, headers)
    group = create_group(client, headers)
    assert replace(client, headers, group["id"], [ingredients[0]["id"]], [dishes[0]["id"]]).status_code == 200

    bad_ingredient = replace(client, headers, group["id"], [str(uuid.uuid4())], [dishes[1]["id"]])
    assert bad_ingredient.status_code == 422
    detail = client.get(f"/api/v1/postpartum/restriction-groups/{group['id']}", headers=headers).json()
    assert [item["id"] for item in detail["ingredients"]] == [ingredients[0]["id"]]
    assert [item["id"] for item in detail["dishes"]] == [dishes[0]["id"]]

    bad_dish = replace(client, headers, group["id"], [ingredients[1]["id"]], [str(uuid.uuid4())])
    assert bad_dish.status_code == 422
    detail = client.get(f"/api/v1/postpartum/restriction-groups/{group['id']}", headers=headers).json()
    assert [item["id"] for item in detail["ingredients"]] == [ingredients[0]["id"]]
    assert [item["id"] for item in detail["dishes"]] == [dishes[0]["id"]]


def test_inactive_existing_targets_can_remain_or_be_removed_but_cannot_be_new(client, db_session):
    headers, _ = auth(client, db_session)
    ingredients, dishes = masters(client, headers)
    group = create_group(client, headers)
    assert replace(client, headers, group["id"], [ingredients[0]["id"]], [dishes[0]["id"]]).status_code == 200
    assert client.post(f"/api/v1/ingredients/{ingredients[0]['id']}/deactivate", headers=headers).status_code == 200
    assert client.post(f"/api/v1/dishes/{dishes[0]['id']}/deactivate", headers=headers).status_code == 200
    retained = replace(client, headers, group["id"], [ingredients[0]["id"]], [dishes[0]["id"]])
    assert retained.status_code == 200
    assert retained.json()["ingredients"][0]["is_active"] is False
    assert retained.json()["dishes"][0]["is_active"] is False
    detail = client.get(f"/api/v1/postpartum/restriction-groups/{group['id']}", headers=headers).json()
    assert detail["ingredients"][0]["is_active"] is False and detail["dishes"][0]["is_active"] is False
    assert replace(client, headers, group["id"], [], []).status_code == 200

    assert client.post(f"/api/v1/ingredients/{ingredients[1]['id']}/deactivate", headers=headers).status_code == 200
    assert client.post(f"/api/v1/dishes/{dishes[1]['id']}/deactivate", headers=headers).status_code == 200
    assert replace(client, headers, group["id"], [ingredients[1]["id"]], []).status_code == 422
    assert replace(client, headers, group["id"], [], [dishes[1]["id"]]).status_code == 422


def test_association_replace_audit_records_actor_and_before_after(client, db_session):
    headers, user = auth(client, db_session)
    ingredients, dishes = masters(client, headers)
    group = create_group(client, headers)
    assert replace(client, headers, group["id"], [ingredients[0]["id"]], [dishes[0]["id"]]).status_code == 200
    audit = db_session.scalar(select(AuditLog).where(
        AuditLog.action == "postpartum_restriction_associations_replace",
        AuditLog.entity_id == group["id"],
    ).order_by(AuditLog.created_at.desc()))
    assert audit is not None and audit.actor_user_id == user.id
    assert audit.before_data == {"ingredient_ids": [], "dish_ids": []}
    assert audit.after_data == {"ingredient_ids": [ingredients[0]["id"]], "dish_ids": [dishes[0]["id"]]}
