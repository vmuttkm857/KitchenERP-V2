import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.audit.models import AuditLog
from app.domains.audit.repository import AuditLogRepository
from app.domains.audit.sanitization import sanitize_audit_data
from app.domains.audit.service import AuditLogService
from app.domains.auth.models import RefreshSession
from app.domains.auth.passwords import verify_password
from app.domains.users.models import User
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "ordinary user password"
NEXT_PASSWORD = "a replacement password"


def create_login(client: TestClient, session: Session, username: str, role: str = "admin"):
    user = UserService(session).create_user(CreateUserCommand(
        username=username, password=ADMIN_PASSWORD if role == "admin" else USER_PASSWORD,
        display_name=f"{username} display", role=role,
    ))
    response = client.post("/api/v1/auth/login", json={
        "username": username, "password": ADMIN_PASSWORD if role == "admin" else USER_PASSWORD,
    })
    assert response.status_code == 200
    return user, {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_users_admin_crud_rbac_passwords_sessions_and_last_admin(
    client: TestClient, db_session: Session,
) -> None:
    admin, headers = create_login(client, db_session, "users-admin")
    created = client.post("/api/v1/users", headers=headers, json={
        "username": "worker.one", "display_name": "第一位工作人員",
        "password": USER_PASSWORD, "confirm_password": USER_PASSWORD, "role": "user",
    })
    assert created.status_code == 201, created.text
    payload = created.json()
    assert "password" not in created.text.lower()
    saved = db_session.get(User, payload["id"])
    assert saved is not None and saved.password_hash != USER_PASSWORD
    assert verify_password(USER_PASSWORD, saved.password_hash)

    duplicate = client.post("/api/v1/users", headers=headers, json={
        "username": "worker.one", "display_name": "重複",
        "password": USER_PASSWORD, "confirm_password": USER_PASSWORD, "role": "user",
    })
    assert duplicate.status_code == 409

    worker_client = TestClient(client.app)
    login = worker_client.post("/api/v1/auth/login", json={"username": "worker.one", "password": USER_PASSWORD})
    worker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert worker_client.get("/api/v1/users", headers=worker_headers).status_code == 403
    assert worker_client.get("/api/v1/audit-logs", headers=worker_headers).status_code == 403
    category = worker_client.post("/api/v1/categories/ingredient", headers=worker_headers,
                                  json={"name": "一般使用者日常分類"})
    assert category.status_code == 201
    assert worker_client.post(
        f"/api/v1/categories/ingredient/{category.json()['id']}/hard-delete",
        headers=worker_headers, json={"password": USER_PASSWORD},
    ).status_code == 403
    assert client.get("/api/v1/users").status_code == 401

    changed = client.patch(f"/api/v1/users/{payload['id']}", headers=headers,
                           json={"display_name": "更新後人員", "role": "user"})
    assert changed.status_code == 200 and changed.json()["username"] == "worker.one"
    assert client.post(f"/api/v1/users/{payload['id']}/deactivate", headers=headers).status_code == 200
    db_session.expire_all()
    assert all(value.revoked_at is not None for value in db_session.scalars(
        select(RefreshSession).where(RefreshSession.user_id == saved.id)
    ))
    assert worker_client.post("/api/v1/auth/refresh").status_code == 401
    assert client.post(f"/api/v1/users/{payload['id']}/reactivate", headers=headers).status_code == 200

    reset = client.post(f"/api/v1/users/{payload['id']}/reset-password", headers=headers, json={
        "current_admin_password": ADMIN_PASSWORD, "new_password": NEXT_PASSWORD,
        "confirm_password": NEXT_PASSWORD,
    })
    assert reset.status_code == 200
    assert client.post("/api/v1/auth/login", json={"username": "worker.one", "password": USER_PASSWORD}).status_code == 401
    relogin = worker_client.post("/api/v1/auth/login", json={"username": "worker.one", "password": NEXT_PASSWORD})
    assert relogin.status_code == 200
    change_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    self_change = worker_client.post("/api/v1/users/me/change-password", headers=change_headers, json={
        "current_password": NEXT_PASSWORD, "new_password": USER_PASSWORD,
        "confirm_password": USER_PASSWORD,
    })
    assert self_change.status_code == 204
    db_session.expire_all()
    sessions = list(db_session.scalars(select(RefreshSession).where(RefreshSession.user_id == saved.id)))
    assert sessions and all(value.revoked_at is not None for value in sessions)

    assert client.patch(f"/api/v1/users/{admin.id}", headers=headers, json={"role": "user"}).status_code == 409
    assert client.post(f"/api/v1/users/{admin.id}/deactivate", headers=headers).status_code == 409


def test_audit_before_after_sanitization_snapshot_filters_and_query_budget(
    client: TestClient, db_session: Session,
) -> None:
    admin, headers = create_login(client, db_session, "audit-admin")
    created = client.post("/api/v1/categories/ingredient",
                          headers={**headers, "X-Forwarded-For": "203.0.113.99"},
                          json={"name": "稽核分類"})
    category_id = created.json()["id"]
    assert client.patch(f"/api/v1/categories/ingredient/{category_id}", headers=headers,
                        json={"name": "稽核分類更新"}).status_code == 200
    assert client.post(f"/api/v1/categories/ingredient/{category_id}/deactivate", headers=headers).status_code == 200
    assert client.post(f"/api/v1/categories/ingredient/{category_id}/reactivate", headers=headers).status_code == 200

    update_log = db_session.scalar(select(AuditLog).where(
        AuditLog.action == "category_update", AuditLog.entity_id == uuid.UUID(category_id)
    ))
    assert update_log is not None
    assert update_log.before_data["name"] == "稽核分類"
    assert update_log.after_data["name"] == "稽核分類更新"
    assert update_log.actor_username == "audit-admin"
    create_log = db_session.scalar(select(AuditLog).where(
        AuditLog.action == "category_create", AuditLog.entity_id == uuid.UUID(category_id)
    ))
    assert create_log is not None and create_log.request_id
    assert create_log.ip_address != "203.0.113.99"
    original_snapshot = update_log.actor_display_name
    admin.display_name = "已修改的顯示名稱"
    db_session.commit(); db_session.refresh(update_log)
    assert update_log.actor_display_name == original_snapshot

    sanitized = sanitize_audit_data({
        "password": "plain", "password_hash": "hash", "access_token": "access",
        "nested": {"refresh_token": "refresh", "safe": "kept"},
    })
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["password_hash"] == "[REDACTED]"
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["nested"]["refresh_token"] == "[REDACTED]"
    assert sanitized["nested"]["safe"] == "kept"

    statements: list[str] = []
    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/v1/audit-logs?page=1&page_size=2&action=category_update"
                              "&entity_type=ingredient_category&keyword=稽核", headers=headers)
    finally:
        event.remove(process_engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 1
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]) <= 3
    detail = client.get(f"/api/v1/audit-logs/{update_log.id}", headers=headers)
    assert detail.status_code == 200 and detail.json()["before_data"]["name"] == "稽核分類"


def test_failed_transaction_does_not_leave_audit(db_session: Session) -> None:
    actor = UserService(db_session).create_user(CreateUserCommand(
        username="rollback-admin", password=ADMIN_PASSWORD,
        display_name="Rollback Admin", role="admin",
    ))
    before = db_session.scalar(select(func.count()).select_from(AuditLog))
    AuditLogService(db_session).record(actor_id=actor.id, action="must_rollback", entity_type="test")
    db_session.add(User(username=actor.username, password_hash="not-used", display_name="Duplicate", role="user"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == before


def test_audit_repository_is_append_only() -> None:
    assert not hasattr(AuditLogRepository, "update")
    assert not hasattr(AuditLogRepository, "delete")
