import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings


@pytest.mark.integration
def test_postgresql_connection() -> None:
    database_url = settings.test_database_url
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        pytest.fail("TEST_DATABASE_URL must point to PostgreSQL; SQLite is forbidden")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
