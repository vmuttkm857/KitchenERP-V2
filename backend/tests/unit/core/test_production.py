from pathlib import Path

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.routes import auth as auth_routes
from app.core.config import Settings
from app.main import create_app


def set_production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://erp:secret@db.internal/kitchenerp")
    monkeypatch.setenv("JWT_SECRET", "production-test-secret-at-least-32-characters")
    monkeypatch.setenv("CORS_ORIGINS", '["https://erp.example.invalid"]')
    monkeypatch.setenv("REFRESH_COOKIE_SECURE", "true")
    monkeypatch.setenv("REFRESH_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("DB_ECHO", "false")


def test_production_missing_secret_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    set_production_environment(monkeypatch)
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("CORS_ORIGINS", '["http://localhost:5173"]', "production origins"),
        ("CORS_ORIGINS", '["*"]', "Wildcard"),
        ("REFRESH_COOKIE_SECURE", "false", "must be true"),
        ("DB_ECHO", "true", "must be false"),
    ],
)
def test_unsafe_production_configuration_fails(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    set_production_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None)


def test_production_cookie_is_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    set_production_environment(monkeypatch)
    production_settings = Settings(_env_file=None)
    monkeypatch.setattr(auth_routes, "settings", production_settings)
    response = Response()
    auth_routes._set_refresh_cookie(response, "opaque-test-token")
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie


def test_development_cookie_can_use_local_http(monkeypatch: pytest.MonkeyPatch) -> None:
    development_settings = Settings(
        _env_file=None,
        app_env="development",
        database_url="postgresql+psycopg://erp@localhost/kitchenerp",
        jwt_secret="development-test-secret-at-least-32-characters",
        refresh_cookie_secure=False,
        cors_origins=["http://localhost:5173"],
    )
    monkeypatch.setattr(auth_routes, "settings", development_settings)
    response = Response()
    auth_routes._set_refresh_cookie(response, "opaque-test-token")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" not in response.headers["set-cookie"]


def test_unexpected_error_does_not_leak_exception_or_secret() -> None:
    test_app = create_app()

    @test_app.get("/_test/unexpected")
    def unexpected() -> None:
        raise RuntimeError("DATABASE_URL=postgresql://user:secret@private-host/db")

    response = TestClient(test_app, raise_server_exceptions=False).get("/_test/unexpected")
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "secret" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_backup_and_restore_scripts_have_required_safety_controls() -> None:
    project_root = Path(__file__).resolve().parents[4]
    backup = (project_root / "scripts" / "backup_postgres.sh").read_text(encoding="utf-8")
    restore = (project_root / "scripts" / "restore_postgres.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in backup
    assert "pg_dump --format=custom" in backup
    assert "kitchenerp_${timestamp}.dump" in backup
    assert "-mtime +6" in backup and "-mtime +27" in backup and "-mtime +92" in backup
    assert "--target-db" in restore and "--dump" in restore
    assert "Refusing to restore" in restore and "--allow-production" in restore
    assert "PGPASSWORD" in restore and '--dbname="${target_db}"' in restore
    assert "pg_restore --exit-on-error" in restore
