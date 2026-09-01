import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
dotenv = dotenv_values(PROJECT_ROOT / ".env")
test_database_url = os.getenv("TEST_DATABASE_URL") or dotenv.get("TEST_DATABASE_URL")
if test_database_url:
    os.environ["TEST_DATABASE_URL"] = test_database_url
    os.environ["DATABASE_URL"] = test_database_url
os.environ.setdefault("JWT_SECRET", "pytest-only-secret-with-at-least-32-characters")

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> Generator[Engine, None, None]:
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL tests")
    if not test_database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        pytest.fail("TEST_DATABASE_URL must point to PostgreSQL; SQLite is forbidden")

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(alembic_config, "head")

    engine = create_engine(test_database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_auth_tables(migrated_test_database: Engine) -> Generator[None, None, None]:
    yield
    with migrated_test_database.begin() as connection:
        connection.execute(text("DELETE FROM audit_logs"))
        connection.execute(text("DELETE FROM purchase_batches"))
        connection.execute(text("DELETE FROM requirement_snapshots"))
        connection.execute(text("DELETE FROM menu_dishes"))
        connection.execute(text("DELETE FROM menu_days"))
        connection.execute(text("DELETE FROM menu_meal_types"))
        connection.execute(text("DELETE FROM menus"))
        connection.execute(text("DELETE FROM dish_ingredients"))
        connection.execute(text("DELETE FROM dishes"))
        connection.execute(text("DELETE FROM ingredient_price_history"))
        connection.execute(text("DELETE FROM ingredient_nutrition_unit_conversions"))
        connection.execute(text("DELETE FROM ingredients"))
        connection.execute(text("DELETE FROM nutrition_food_values"))
        connection.execute(text("DELETE FROM nutrition_foods"))
        connection.execute(text("DELETE FROM nutrition_nutrients"))
        connection.execute(text("DELETE FROM nutrition_import_batches"))
        connection.execute(text("DELETE FROM suppliers"))
        connection.execute(text("DELETE FROM menu_categories"))
        connection.execute(text("DELETE FROM dish_categories"))
        connection.execute(text("DELETE FROM categories"))
        connection.execute(text("DELETE FROM refresh_sessions"))
        connection.execute(text("DELETE FROM users"))


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
