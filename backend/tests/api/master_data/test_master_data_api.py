import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.ingredients.models import Ingredient
from app.domains.ingredients.repository import IngredientRepository
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


def test_ingredient_name_uniqueness_create_update_inactive_code_and_database(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    headers, actor_id = auth_headers(client, db_session)
    category, supplier, first = create_chain(client, headers)
    second = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ING-02", "name": "豬肉", "category_id": category["id"], "unit": "kg",
        "current_price": "100", "primary_supplier_id": supplier["id"],
    })
    assert second.status_code == 201, second.text

    duplicate_name = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ING-03", "name": "  雞肉  ", "category_id": category["id"], "unit": "kg", "current_price": "1",
    })
    assert duplicate_name.status_code == 409
    assert duplicate_name.json()["detail"] == "食材名稱已存在"
    assert client.patch(f"/api/v1/ingredients/{first['id']}", headers=headers, json={"name": "雞肉"}).status_code == 200
    update_to_existing = client.patch(f"/api/v1/ingredients/{first['id']}", headers=headers, json={"name": "豬肉"})
    assert update_to_existing.status_code == 409
    assert update_to_existing.json()["detail"] == "食材名稱已存在"

    assert client.post(f"/api/v1/ingredients/{first['id']}/deactivate", headers=headers).status_code == 200
    inactive_duplicate = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ING-04", "name": "雞肉", "category_id": category["id"], "unit": "kg", "current_price": "1",
    })
    assert inactive_duplicate.status_code == 409
    duplicate_code = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ing-02", "name": "不同名稱", "category_id": category["id"], "unit": "kg", "current_price": "1",
    })
    assert duplicate_code.status_code == 409
    assert duplicate_code.json()["detail"] == "Ingredient code already exists"

    monkeypatch.setattr(IngredientRepository, "name_exists", lambda self, name, exclude_id=None: False)
    race_duplicate = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ING-RACE", "name": "豬肉", "category_id": category["id"], "unit": "kg", "current_price": "1",
    })
    assert race_duplicate.status_code == 409
    assert race_duplicate.json()["detail"] == "食材名稱已存在"

    db_session.add(Ingredient(
        code="ING-DB", name=" 豬肉 ", category_id=uuid.UUID(category["id"]), unit="kg",
        current_price=1, created_by=uuid.UUID(actor_id), updated_by=uuid.UUID(actor_id),
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


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


def test_ingredient_list_supplier_filter_combinations_and_pagination(client: TestClient, db_session: Session) -> None:
    headers, _ = auth_headers(client, db_session)
    category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "蔬菜"}).json()
    other_category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "乾貨"}).json()
    supplier = client.post("/api/v1/suppliers", headers=headers, json={"code": "SUP-A", "name": "甲供應商"}).json()
    other_supplier = client.post("/api/v1/suppliers", headers=headers, json={"code": "SUP-B", "name": "乙供應商"}).json()

    def create_ingredient(code: str, name: str, category_id: str, supplier_id: str) -> None:
        response = client.post("/api/v1/ingredients", headers=headers, json={
            "code": code, "name": name, "category_id": category_id, "unit": "kg",
            "current_price": "10", "primary_supplier_id": supplier_id,
            "purchase_unit": "kg", "package_size": "1", "minimum_order_quantity": "0",
        })
        assert response.status_code == 201, response.text

    create_ingredient("VEG-01", "青菜一號", category["id"], supplier["id"])
    create_ingredient("VEG-02", "青菜二號", category["id"], supplier["id"])
    create_ingredient("DRY-01", "乾貨一號", other_category["id"], supplier["id"])
    create_ingredient("OTHER-01", "其他食材", category["id"], other_supplier["id"])

    filtered = client.get(
        f"/api/v1/ingredients?supplier_id={supplier['id']}&category_id={category['id']}&search=青菜&page=1&page_size=1",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total"] == 2
    assert len(filtered.json()["items"]) == 1

    second_page = client.get(
        f"/api/v1/ingredients?supplier_id={supplier['id']}&category_id={category['id']}&search=青菜&page=2&page_size=1",
        headers=headers,
    )
    assert second_page.status_code == 200
    assert second_page.json()["pagination"]["total"] == 2
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["items"][0]["id"] != filtered.json()["items"][0]["id"]

    statements: list[str] = []
    def record_query(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record_query)
    try:
        response = client.get(
            f"/api/v1/ingredients?supplier_id={supplier['id']}&category_id={category['id']}&page=1&page_size=25",
            headers=headers,
        )
    finally:
        event.remove(process_engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 2
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 3
