from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0017_to_0018_expands_postpartum_meal_constraints(migrated_test_database):
    command.downgrade(config(), "20260909_0017")
    try:
        command.upgrade(config(), "20260909_0018")
        with migrated_test_database.begin() as connection:
            constraints = connection.execute(text("""
                SELECT conname, pg_get_constraintdef(oid) AS definition
                FROM pg_constraint
                WHERE conname IN (
                    'ck_postpartum_cases_start_meal',
                    'ck_postpartum_cases_end_meal',
                    'ck_postpartum_room_histories_meal',
                    'ck_postpartum_service_pauses_start_meal',
                    'ck_postpartum_service_pauses_end_meal'
                )
            """)).mappings().all()
            assert len(constraints) == 5
            assert all("morning_snack" in item["definition"] for item in constraints)
            assert all("afternoon_snack" in item["definition"] for item in constraints)
            assert all("evening_snack" in item["definition"] for item in constraints)
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260909_0018"
    finally:
        command.upgrade(config(), "head")
