from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.users.models import User
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def create_admin(db_session: Session) -> User:
    return UserService(db_session).create_user(
        CreateUserCommand(
            username="admin",
            password=PASSWORD,
            display_name="Kitchen Admin",
            role="admin",
        )
    )


def login(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def test_login_success_me_and_no_password_hash(
    client: TestClient, db_session: Session
) -> None:
    create_admin(db_session)
    payload = login(client)

    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert payload["user"]["display_name"] == "Kitchen Admin"
    assert "password" not in str(payload).lower()

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "admin"
    assert "password_hash" not in me_response.text


def test_login_wrong_password(client: TestClient, db_session: Session) -> None:
    create_admin(db_session)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong password"},
    )
    assert response.status_code == 401
    assert "password" not in response.text.lower()


def test_inactive_user_cannot_login(client: TestClient, db_session: Session) -> None:
    user = create_admin(db_session)
    db_session.execute(update(User).where(User.id == user.id).values(is_active=False))
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": PASSWORD},
    )
    assert response.status_code == 401


def test_refresh_rotation_invalidates_old_token(
    client: TestClient, db_session: Session
) -> None:
    create_admin(db_session)
    login(client)
    old_refresh = client.cookies.get(settings.refresh_cookie_name)
    assert old_refresh

    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    new_refresh = client.cookies.get(settings.refresh_cookie_name)
    assert new_refresh and new_refresh != old_refresh

    replay_client = TestClient(client.app)
    replay_client.cookies.set(
        settings.refresh_cookie_name,
        old_refresh,
        path="/api/v1/auth",
    )
    replay_response = replay_client.post("/api/v1/auth/refresh")
    assert replay_response.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, db_session: Session) -> None:
    create_admin(db_session)
    login(client)
    refresh_token = client.cookies.get(settings.refresh_cookie_name)
    assert refresh_token

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    assert client.cookies.get(settings.refresh_cookie_name) is None

    replay_client = TestClient(client.app)
    replay_client.cookies.set(
        settings.refresh_cookie_name,
        refresh_token,
        path="/api/v1/auth",
    )
    assert replay_client.post("/api/v1/auth/refresh").status_code == 401
