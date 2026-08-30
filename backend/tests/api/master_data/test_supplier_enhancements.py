import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.ingredients.models import Ingredient
from app.domains.suppliers.models import Supplier
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def auth_headers(client: TestClient, db_session: Session) -> tuple[dict[str, str], str]:
    user = UserService(db_session).create_user(CreateUserCommand(
        username="supplier_admin", password=PASSWORD, display_name="Supplier Admin", role="admin",
    ))
    response = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, str(user.id)


def create_supplier(client: TestClient, headers: dict[str, str], code: str, name: str, **extra):
    response = client.post("/api/v1/suppliers", headers=headers, json={"code": code, "name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_supplier_fields_ordering_filters_pagination_and_query_budget(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    first = create_supplier(
        client, headers, "SUP-B", "乙供應商", contact_person="王小姐", phone="02-1111",
        address="台北市中山區", notes="下午送貨", is_active=False,
    )
    second = create_supplier(client, headers, "SUP-A", "甲供應商")

    assert first["contact_person"] == "王小姐"
    assert first["address"] == "台北市中山區"
    assert first["notes"] == "下午送貨"
    assert first["is_active"] is False
    assert first["sort_order"] == 1 and second["sort_order"] == 2

    updated = client.patch(f"/api/v1/suppliers/{first['id']}", headers=headers, json={
        "contact_person": "林先生", "phone": "02-2222", "address": "新北市板橋區",
        "notes": "請先電話聯絡", "is_active": True,
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["contact_person"] == "林先生"
    assert updated.json()["address"] == "新北市板橋區"
    assert updated.json()["updated_by"] == actor_id

    db_session.execute(update(Supplier).values(sort_order=1))
    db_session.commit()
    inactive = client.post(f"/api/v1/suppliers/{first['id']}/deactivate", headers=headers)
    assert inactive.status_code == 200 and inactive.json()["sort_order"] == 1

    statements: list[str] = []
    def record_query(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record_query)
    try:
        listed = client.get("/api/v1/suppliers?search=供應商&active=true&page=1&page_size=1", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record_query)
    assert listed.status_code == 200
    assert listed.json()["pagination"] == {"page": 1, "page_size": 1, "total": 1}
    assert listed.json()["items"][0]["id"] == second["id"]
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 3

    all_rows = client.get("/api/v1/suppliers?page=1&page_size=25", headers=headers).json()["items"]
    assert [row["code"] for row in all_rows] == ["SUP-A", "SUP-B"]
    assert next(row for row in all_rows if row["id"] == first["id"])["is_active"] is False


def test_supplier_reorder_is_atomic_audited_and_keeps_ingredient_reference(client: TestClient, db_session: Session) -> None:
    headers, actor_id = auth_headers(client, db_session)
    first = create_supplier(client, headers, "SUP-1", "供應商一")
    second = create_supplier(client, headers, "SUP-2", "供應商二")
    third = create_supplier(client, headers, "SUP-3", "供應商三")
    original = [first["id"], second["id"], third["id"]]

    category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "排序測試分類"}).json()
    ingredient = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "ORDER-ING", "name": "排序測試食材", "category_id": category["id"],
        "unit": "kg", "current_price": "1", "primary_supplier_id": first["id"],
    })
    assert ingredient.status_code == 201, ingredient.text

    assert client.post("/api/v1/suppliers/reorder", json={"supplier_ids": original}).status_code == 401
    assert client.post("/api/v1/suppliers/reorder", headers=headers, json={"supplier_ids": [first["id"], first["id"], third["id"]]}).status_code == 422
    assert client.post("/api/v1/suppliers/reorder", headers=headers, json={"supplier_ids": [first["id"], third["id"]]}).status_code == 422
    assert client.post("/api/v1/suppliers/reorder", headers=headers, json={"supplier_ids": [first["id"], second["id"], str(uuid.uuid4())]}).status_code == 422
    assert client.get("/api/v1/suppliers/order", headers=headers).json() == original

    db_session.execute(update(Supplier).values(updated_at="2020-01-01 00:00:00+00"))
    db_session.commit()
    reordered = [third["id"], first["id"], second["id"]]
    response = client.post("/api/v1/suppliers/reorder", headers=headers, json={"supplier_ids": reordered})
    assert response.status_code == 204, response.text
    assert client.get("/api/v1/suppliers/order", headers=headers).json() == reordered

    suppliers = db_session.scalars(select(Supplier).order_by(Supplier.sort_order)).all()
    assert [str(row.id) for row in suppliers] == reordered
    assert [row.sort_order for row in suppliers] == [1, 2, 3]
    assert all(str(row.updated_by) == actor_id for row in suppliers)
    assert all(row.updated_at.year > 2020 for row in suppliers)
    saved_ingredient = db_session.get(Ingredient, uuid.UUID(ingredient.json()["id"]))
    assert saved_ingredient is not None
    assert str(saved_ingredient.primary_supplier_id) == first["id"]


def test_supplier_reorder_repository_failure_rolls_back_all_rows(client: TestClient, db_session: Session, monkeypatch) -> None:
    headers, _ = auth_headers(client, db_session)
    first = create_supplier(client, headers, "SUP-X", "供應商 X")
    second = create_supplier(client, headers, "SUP-Y", "供應商 Y")

    from app.domains.suppliers.repository import SupplierRepository
    original_reorder = SupplierRepository.reorder
    def fail_after_update(self, supplier_ids, actor_id):
        original_reorder(self, supplier_ids, actor_id)
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(SupplierRepository, "reorder", fail_after_update)

    response = client.post("/api/v1/suppliers/reorder", headers=headers, json={"supplier_ids": [second["id"], first["id"]]})
    assert response.status_code == 400
    db_session.expire_all()
    rows = db_session.scalars(select(Supplier).order_by(Supplier.sort_order)).all()
    assert [str(row.id) for row in rows] == [first["id"], second["id"]]
