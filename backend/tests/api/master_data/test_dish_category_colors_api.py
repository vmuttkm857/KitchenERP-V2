"""Persistence/API checks, only inside the approved disposable regression DB."""
import uuid

from sqlalchemy import select

from app.domains.audit.models import AuditLog
from tests.api.master_data.test_master_data_api import auth_headers
from tests.api.menus.test_menu_meal_slot_api import _setup, _url, _payload


def test_category_color_persists_create_update_clear_audit_and_inactive(client, db_session):
    headers, _ = auth_headers(client, db_session)
    created = client.post("/api/v1/categories/dish", headers=headers, json={"name":"測試背景","background_color":"#bbdefb"})
    assert created.status_code == 201
    category_id = created.json()["id"]
    assert created.json()["background_color"] == "#BBDEFB"
    path = f"/api/v1/categories/dish/{category_id}"
    assert client.patch(path, headers=headers, json={"name":"重新命名","sort_order":10}).json()["background_color"] == "#BBDEFB"
    assert client.post(path + "/deactivate", headers=headers).json()["background_color"] == "#BBDEFB"
    assert client.get(path, headers=headers).json()["background_color"] == "#BBDEFB"
    assert client.patch(path, headers=headers, json={"background_color":"invalid"}).status_code == 422
    assert client.patch(path, headers=headers, json={"background_color":None}).json()["background_color"] is None
    logs = list(db_session.scalars(select(AuditLog).where(AuditLog.entity_id == uuid.UUID(category_id), AuditLog.action == "category_update")))
    assert any(log.before_data.get("background_color") == "#BBDEFB" and log.after_data.get("background_color") is None for log in logs)
    other = client.post("/api/v1/categories/menu", headers=headers, json={"name":"其他分類"})
    assert "background_color" not in other.json()
    assert client.patch(f"/api/v1/categories/menu/{other.json()['id']}", headers=headers, json={"background_color":"#BBDEFB"}).status_code == 422


def test_color_change_does_not_invalidate_real_menu_or_slot_versions(client, db_session):
    headers, menu, meal, _, dishes = _setup(client, db_session)
    path = _url(menu, meal)
    before = client.get(path, headers=headers).json()
    editor_path = f"/api/v1/menus/{menu['id']}/editor"
    before_editor = client.get(editor_path, headers=headers).json()
    category_id = dishes[0]["category_id"]
    assert before["dish_category_ids"][dishes[0]["id"]] == category_id
    changed = client.patch(f"/api/v1/categories/dish/{category_id}", headers=headers, json={"background_color":"#FCE4EC"})
    assert changed.status_code == 200
    after = client.get(path, headers=headers).json()
    assert after == before
    assert client.get(editor_path, headers=headers).json()["editor_fingerprint"] == before_editor["editor_fingerprint"]
    response = client.put(path, headers=headers, json=_payload(before, notes="顏色變更後仍可儲存"))
    assert response.status_code == 200
    assert client.put(path, headers=headers, json=_payload(before, notes="過期版本不能覆蓋")).status_code == 409
