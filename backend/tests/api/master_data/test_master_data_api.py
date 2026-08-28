from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def auth_headers(client: TestClient, db_session: Session) -> tuple[dict[str, str], str]:
    user = UserService(db_session).create_user(CreateUserCommand(username="master_admin", password=PASSWORD, display_name="Master Admin", role="admin"))
    response = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, str(user.id)


def create_chain(client: TestClient, headers: dict[str, str]):
    category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "肉類", "sort_order": 1})
    supplier = client.post("/api/v1/suppliers", headers=headers, json={"code": "SUP-01", "name": "第一供應商"})
    assert category.status_code == supplier.status_code == 201
    ingredient = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ING-01", "name": "雞肉", "category_id": category.json()["id"], "unit": "kg",
        "current_price": "120.50", "primary_supplier_id": supplier.json()["id"],
        "purchase_unit": "kg", "package_size": "1", "minimum_order_quantity": "0",
    })
    assert ingredient.status_code == 201, ingredient.text
    return category.json(), supplier.json(), ingredient.json()


def test_writes_require_authentication(client: TestClient) -> None:
    assert client.post("/api/v1/categories/ingredient", json={"name": "未授權"}).status_code == 401
    assert client.post("/api/v1/suppliers", json={"code": "NO", "name": "未授權"}).status_code == 401


def test_categories_crud_unique_actors_and_hard_delete(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    created = client.post("/api/v1/categories/dish", headers=headers, json={"name": "主菜", "sort_order": 2})
    assert created.status_code == 201
    assert created.json()["created_by"] == actor_id
    assert client.post("/api/v1/categories/dish", headers=headers, json={"name": "主菜"}).status_code == 409
    category_id = created.json()["id"]
    updated = client.patch(f"/api/v1/categories/dish/{category_id}", headers=headers, json={"name": "主餐", "sort_order": 3})
    assert updated.json()["updated_by"] == actor_id
    assert client.post(f"/api/v1/categories/dish/{category_id}/deactivate", headers=headers).json()["is_active"] is False
    assert client.post(f"/api/v1/categories/dish/{category_id}/reactivate", headers=headers).json()["is_active"] is True
    assert client.post(f"/api/v1/categories/dish/{category_id}/hard-delete", headers=headers, json={"password": "wrong"}).status_code == 401
    assert client.post(f"/api/v1/categories/dish/{category_id}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 204


def test_supplier_crud_and_hard_delete(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    created = client.post("/api/v1/suppliers", headers=headers, json={"code": "s-1", "name": "供應商", "phone": "123"})
    assert created.status_code == 201 and created.json()["code"] == "S-1"
    supplier_id = created.json()["id"]
    updated = client.patch(f"/api/v1/suppliers/{supplier_id}", headers=headers, json={"name": "新供應商"})
    assert updated.json()["updated_by"] == actor_id
    assert client.post(f"/api/v1/suppliers/{supplier_id}/deactivate", headers=headers).json()["is_active"] is False
    assert client.post(f"/api/v1/suppliers/{supplier_id}/reactivate", headers=headers).json()["is_active"] is True
    assert client.post(f"/api/v1/suppliers/{supplier_id}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 204


def test_ingredient_price_history_activation_and_delete_policy(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    category, supplier, ingredient = create_chain(client, headers)
    assert ingredient["current_price"] == "120.5000"
    assert ingredient["category_name"] == "肉類"
    assert ingredient["supplier_name"] == "第一供應商"
    assert ingredient["created_by"] == actor_id

    history = client.get(f"/api/v1/ingredients/{ingredient['id']}/price-history", headers=headers)
    assert len(history.json()) == 1 and history.json()[0]["price"] == "120.5000"
    updated = client.patch(f"/api/v1/ingredients/{ingredient['id']}", headers=headers, json={"current_price": "135.25", "price_notes": "調價"})
    assert updated.status_code == 200 and updated.json()["updated_by"] == actor_id
    history = client.get(f"/api/v1/ingredients/{ingredient['id']}/price-history", headers=headers)
    assert [row["price"] for row in history.json()] == ["135.2500", "120.5000"]
    assert client.post(f"/api/v1/ingredients/{ingredient['id']}/deactivate", headers=headers).json()["is_active"] is False
    assert client.post(f"/api/v1/ingredients/{ingredient['id']}/reactivate", headers=headers).json()["is_active"] is True
    assert client.post(f"/api/v1/ingredients/{ingredient['id']}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 409
    assert client.post(f"/api/v1/categories/ingredient/{category['id']}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 409
    assert client.post(f"/api/v1/suppliers/{supplier['id']}/hard-delete", headers=headers, json={"password": PASSWORD}).status_code == 409


def test_inactive_references_cannot_be_selected(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "停用分類"}).json()
    client.post(f"/api/v1/categories/ingredient/{category['id']}/deactivate", headers=headers)
    response = client.post("/api/v1/ingredients", headers=headers, json={"code": "BAD", "name": "不應建立", "category_id": category["id"], "unit": "kg", "current_price": "1"})
    assert response.status_code == 422


def test_ingredient_list_has_constant_query_count(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    create_chain(client, headers)
    statements: list[str] = []
    def record_query(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record_query)
    try:
        response = client.get("/api/v1/ingredients?page=1&page_size=25", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 3
    assert "password_hash" not in response.text
