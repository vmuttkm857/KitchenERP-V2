import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("JWT_SECRET", "pytest-only-secret-with-at-least-32-characters")

from tests.database_safety import (  # noqa: E402
    UnsafeTestDatabase, guarded_migration, test_database_target,
    validate_engine_target, verify_connection,
)
from tests.connection_diagnostics import open_verified_connection  # noqa: E402


def pytest_addoption(parser):
    group = parser.getgroup("isolated PostgreSQL tests")
    group.addoption("--database-tests", action="store_true", help="Use an approved disposable regression database")
    group.addoption("--migration-tests", action="store_true", help="Use an approved disposable migration database")


def pytest_configure(config):
    migration = config.getoption("--migration-tests")
    regression = config.getoption("--database-tests")
    if migration and regression:
        raise pytest.UsageError("Run migration and regression databases in separate pytest processes")
    target = None
    if migration or regression:
        try:
            target = test_database_target("migration" if migration else "regression", os.environ)
        except UnsafeTestDatabase as error:
            raise pytest.UsageError(str(error)) from None
    config._isolated_database_target = target
    patch = pytest.MonkeyPatch()
    config._database_safety_patch = patch
    original_connect = Engine.connect
    application_name = f"kitchenerp-pytest:{os.getpid()}"

    def safe_connect(engine, *args, **kwargs):
        validate_engine_target(target, engine.url)
        if test_database_target(target.kind, os.environ) != target:
            raise UnsafeTestDatabase("TEST_DB_CONFIGURATION_CHANGED")
        return open_verified_connection(original_connect, engine, target, application_name, *args, verify=verify_connection, **kwargs)

    patch.setattr(Engine, "connect", safe_connect)
    for operation in ("upgrade", "downgrade"):
        original = getattr(command, operation)

        def safe_migration(alembic_config, *args, _operation=operation, _original=original, **kwargs):
            from app.core.config import settings
            if target is not None:
                validate_engine_target(target, make_url(settings.database_url))
                validate_engine_target(target, make_url(settings.test_database_url or ""))

            def verified_invoke(*call_args, **call_kwargs):
                # Preflight actual identity before entering Alembic. Engine.connect
                # also verifies env.py's separate connection before any DDL.
                probe = create_engine(target.url, pool_pre_ping=True)
                try:
                    with probe.connect():
                        return _original(*call_args, **call_kwargs)
                finally:
                    probe.dispose()

            return guarded_migration(_operation, verified_invoke, target, os.environ, alembic_config, *args, **kwargs)

        patch.setattr(command, operation, safe_migration)


def pytest_unconfigure(config):
    patch = getattr(config, "_database_safety_patch", None)
    if patch:
        patch.undo()


def pytest_collection_modifyitems(config, items):
    for item in items:
        migration = item.path.name.endswith("_migration.py")
        unit = "unit" in item.path.relative_to(BACKEND_ROOT / "tests").parts
        if migration:
            item.add_marker(pytest.mark.migration)
        if migration and not config.getoption("--migration-tests"):
            item.add_marker(pytest.mark.skip(reason="Dedicated migration database and --migration-tests approval required"))
        elif not unit and not migration and not config.getoption("--database-tests"):
            item.add_marker(pytest.mark.skip(reason="Dedicated regression database and --database-tests approval required"))


@pytest.fixture(scope="session")
def migrated_test_database(pytestconfig) -> Generator[Engine, None, None]:
    target = pytestconfig._isolated_database_target
    if target is None:
        pytest.skip("No disposable database explicitly configured")
    from app.core.config import settings
    validate_engine_target(target, make_url(settings.database_url))
    engine = create_engine(target.url, pool_pre_ping=True)
    # Verify the actual endpoint, role, ownership, disposable marker and other
    # sessions BEFORE any schema change or existing cleanup fixture can run.
    with engine.connect():
        pass

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    try:
        if target.kind == "migration":
            command.upgrade(alembic_config, "head")
        else:
            from alembic.script import ScriptDirectory
            expected = ScriptDirectory.from_config(alembic_config).get_current_head()
            with engine.connect() as connection:
                if connection.scalar(text("SELECT version_num FROM alembic_version")) != expected:
                    pytest.fail("REGRESSION_DB_MUST_ALREADY_BE_AT_HEAD; no automatic migration")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_auth_tables(request) -> Generator[None, None, None]:
    if "unit" in request.path.relative_to(BACKEND_ROOT / "tests").parts:
        yield
        return
    migrated_test_database = request.getfixturevalue("migrated_test_database")
    yield
    with migrated_test_database.begin() as connection:
        connection.execute(text("DELETE FROM audit_logs"))
        connection.execute(text("DELETE FROM postpartum_conflict_handlings"))
        connection.execute(text("DELETE FROM postpartum_replacement_groups"))
        connection.execute(text("DELETE FROM postpartum_menu_meal_mappings"))
        connection.execute(text("DELETE FROM postpartum_menu_sources"))
        connection.execute(text("DELETE FROM postpartum_case_restriction_groups"))
        connection.execute(text("DELETE FROM postpartum_restriction_group_dishes"))
        connection.execute(text("DELETE FROM postpartum_restriction_group_ingredients"))
        connection.execute(text("DELETE FROM postpartum_restriction_groups"))
        connection.execute(text("DELETE FROM postpartum_service_pauses"))
        connection.execute(text("DELETE FROM postpartum_room_histories"))
        connection.execute(text("DELETE FROM postpartum_cases"))
        connection.execute(text("DELETE FROM postpartum_service_pauses"))
        connection.execute(text("DELETE FROM postpartum_room_histories"))
        connection.execute(text("DELETE FROM postpartum_cases"))
        connection.execute(text("DELETE FROM production_process_steps"))
        connection.execute(text("DELETE FROM production_batch_ingredients"))
        connection.execute(text("DELETE FROM production_batch_versions"))
        connection.execute(text("DELETE FROM dish_production_profiles"))
        connection.execute(text("DELETE FROM purchase_batches"))
        connection.execute(text("DELETE FROM menu_import_lines"))
        connection.execute(text("DELETE FROM menu_import_batches"))
        connection.execute(text("DELETE FROM ordering_adjustment_lines"))
        connection.execute(text("DELETE FROM ordering_adjustment_sheets"))
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
    from app.db.session import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
