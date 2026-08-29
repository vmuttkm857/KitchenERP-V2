from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def auth_headers(client: TestClient, db_session: Session) -> tuple[dict[str, str], str]:
    user = UserService(db_session).create_user(CreateUserCommand(
        username="recipe_admin", password=PASSWORD, display_name="Recipe Admin", role="admin"
    ))
    response = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, str(user.id)


def foundations(client: TestClient, headers: dict[str, str]):
    dish_category = client.post("/api/v1/categories/dish", headers=headers, json={"name": "主菜"}).json()
    ingredient_category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "食材"}).json()
    supplier = client.post("/api/v1/suppliers", headers=headers, json={"code": "SUP-R", "name": "配方供應商"}).json()
    ingredients = []
    for index, (name, unit, price) in enumerate((("雞肉", "kg", "120"), ("鹽", "kg", "20"), ("水", "L", "1")), 1):
        response = client.post("/api/v1/ingredients", headers=headers, json={
            "code": f"R-{index}", "name": name, "category_id": ingredient_category["id"],
            "unit": unit, "current_price": price, "primary_supplier_id": supplier["id"],
        })
        assert response.status_code == 201, response.text
        ingredients.append(response.json())
    return dish_category, ingredients


def create_dish(client: TestClient, headers: dict[str, str], category_id: str):
    response = client.post("/api/v1/dishes", headers=headers, json={
        "code": "D-001", "name": "香煎雞肉", "category_id": category_id, "notes": "測試菜色"
    })
    assert response.status_code == 201, response.text
    return response.json()


def recipe_payload(ingredients: list[dict]) -> dict:
    return {"items": [
        {"ingredient_id": ingredients[0]["id"], "quantity": "0.500000", "unit": "kg", "loss_rate": "10.000000", "sort_order": 2, "notes": "主料"},
        {"ingredient_id": ingredients[1]["id"], "quantity": "5.000000", "unit": "g", "loss_rate": "0", "sort_order": 1},
    ]}


def test_dishes_and_recipes_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/dishes").status_code == 401
    assert client.put("/api/v1/dishes/00000000-0000-0000-0000-000000000001/recipe", json={"items": []}).status_code == 401


def test_dish_crud_validation_activation_and_delete_policy(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    assert dish["created_by"] == actor_id and dish["category_name"] == "主菜"
    assert client.post("/api/v1/dishes", headers=headers, json={"code": "D-001", "name": "另一道"}).status_code == 409
    assert client.post("/api/v1/dishes", headers=headers, json={"code": "D-002", "name": "香煎雞肉"}).status_code == 409
    updated = client.patch(f"/api/v1/dishes/{dish['id']}", headers=headers, json={"name": "香煎雞腿"})
    assert updated.status_code == 200 and updated.json()["updated_by"] == actor_id
    assert client.post(f"/api/v1/dishes/{dish['id']}/deactivate", headers=headers).json()["is_active"] is False
    assert client.post(f"/api/v1/dishes/{dish['id']}/reactivate", headers=headers).json()["is_active"] is True
    client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=recipe_payload(ingredients))
    assert client.post(f"/api/v1/dishes/{dish['id']}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 409
    assert client.post(f"/api/v1/categories/dish/{category['id']}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 409


def test_inactive_dish_category_is_rejected(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category = client.post("/api/v1/categories/dish", headers=headers, json={"name": "停用菜色分類"}).json()
    client.post(f"/api/v1/categories/dish/{category['id']}/deactivate", headers=headers)
    response = client.post("/api/v1/dishes", headers=headers, json={"code": "BAD", "name": "不應建立", "category_id": category["id"]})
    assert response.status_code == 422


def test_recipe_replace_decimal_sort_relationship_removal_and_actors(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    created = client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=recipe_payload(ingredients))
    assert created.status_code == 200, created.text
    body = created.json()
    assert [item["ingredient_name"] for item in body["items"]] == ["鹽", "雞肉"]
    assert body["items"][0]["quantity"] == "5.000000"
    assert body["items"][1]["loss_rate"] == "10.000000"
    assert body["items"][1]["created_by"] == actor_id
    assert Decimal(body["total_cost"]) == Decimal("66.1") and body["requirement_ready"] is True

    retained = body["items"][1]
    replacement = {"items": [{
        "id": retained["id"], "ingredient_id": retained["ingredient_id"],
        "quantity": "0.750000", "unit": "kg", "loss_rate": "5", "sort_order": 1,
    }]}
    updated = client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=replacement)
    assert updated.status_code == 200
    assert len(updated.json()["items"]) == 1
    assert updated.json()["items"][0]["id"] == retained["id"]
    assert updated.json()["items"][0]["updated_by"] == actor_id
    assert client.get(f"/api/v1/ingredients/{ingredients[1]['id']}", headers=headers).status_code == 200


def test_recipe_duplicate_invalid_values_and_inactive_ingredient_are_rejected(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    duplicate = {"items": [
        {"ingredient_id": ingredients[0]["id"], "quantity": "1", "unit": "kg", "loss_rate": "0"},
        {"ingredient_id": ingredients[0]["id"], "quantity": "2", "unit": "kg", "loss_rate": "0"},
    ]}
    assert client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=duplicate).status_code == 409
    assert client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{"ingredient_id": ingredients[0]["id"], "quantity": "-1", "unit": "kg", "loss_rate": "0"}]}).status_code == 422
    assert client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{"ingredient_id": ingredients[0]["id"], "quantity": "1", "unit": "kg", "loss_rate": "-1"}]}).status_code == 422
    assert client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{"ingredient_id": ingredients[0]["id"], "quantity": "1", "unit": "mL", "loss_rate": "0"}]}).status_code == 422
    client.post(f"/api/v1/ingredients/{ingredients[0]['id']}/deactivate", headers=headers)
    assert client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{"ingredient_id": ingredients[0]["id"], "quantity": "1", "unit": "kg", "loss_rate": "0"}]}).status_code == 422


def test_recipe_draft_zero_is_saved_but_not_requirement_ready(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    response = client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{
        "ingredient_id": ingredients[0]["id"], "quantity": "0", "unit": "kg", "loss_rate": "0"
    }]})
    assert response.status_code == 200 and response.json()["requirement_ready"] is False


def test_recipe_replace_is_atomic(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    client.post(f"/api/v1/ingredients/{ingredients[1]['id']}/deactivate", headers=headers)
    payload = {"items": [
        {"ingredient_id": ingredients[0]["id"], "quantity": "1", "unit": "kg", "loss_rate": "0"},
        {"ingredient_id": ingredients[1]["id"], "quantity": "1", "unit": "kg", "loss_rate": "0"},
    ]}
    assert client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=payload).status_code == 422
    empty_recipe = client.get(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers).json()
    assert empty_recipe["items"] == [] and empty_recipe["requirement_ready"] is False


def test_recipe_aggregate_query_count_is_constant(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=recipe_payload(ingredients))
    statements: list[str] = []
    def record_query(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record_query)
    try:
        response = client.get(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 3  # current user + dish/category aggregate + recipe/ingredient/supplier aggregate
    assert "password_hash" not in response.text


def test_dish_list_includes_recipe_ingredient_count_with_fixed_query_budget(
    client: TestClient, db_session: Session,
) -> None:
    headers, _ = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    empty_dish = create_dish(client, headers, category["id"])
    recipe_dish = client.post("/api/v1/dishes", headers=headers, json={
        "code": "D-002", "name": "有配方菜色", "category_id": category["id"],
    }).json()
    client.put(f"/api/v1/dishes/{recipe_dish['id']}/recipe", headers=headers, json=recipe_payload(ingredients))

    statements: list[str] = []

    def record_query(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(process_engine, "before_cursor_execute", record_query)
    try:
        response = client.get("/api/v1/dishes?page_size=100", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record_query)

    assert response.status_code == 200
    dishes = {item["id"]: item for item in response.json()["items"]}
    assert dishes[empty_dish["id"]]["recipe_ingredient_count"] == 0
    assert dishes[recipe_dish["id"]]["recipe_ingredient_count"] == 2
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 3  # current user + pagination total + one projected dish list query


def test_database_fk_restricts_recipe_ingredient_deletion(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category, ingredients = foundations(client, headers)
    dish = create_dish(client, headers, category["id"])
    client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json=recipe_payload(ingredients))
    referenced = db_session.execute(
        text("SELECT count(*) FROM dish_ingredients WHERE ingredient_id = :id"),
        {"id": ingredients[0]["id"]},
    ).scalar_one()
    delete_action = db_session.execute(text("""
        SELECT confdeltype FROM pg_constraint
        WHERE conname = 'dish_ingredients_ingredient_id_fkey'
    """)).scalar_one()
    assert referenced == 1
    assert delete_action == "r"
