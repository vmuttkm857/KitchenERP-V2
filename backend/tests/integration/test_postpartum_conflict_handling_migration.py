from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0019_to_0020_adds_replacement_and_conflict_handling_schema(migrated_test_database):
    command.downgrade(config(), "20260909_0019")
    try:
        command.upgrade(config(), "20260911_0020")
        inspector = inspect(migrated_test_database)
        assert inspector.has_table("postpartum_replacement_groups")
        assert inspector.has_table("postpartum_conflict_handlings")
        handling_columns = {item["name"]: item for item in inspector.get_columns("postpartum_conflict_handlings")}
        assert handling_columns["replacement_group_id"]["nullable"] is True
        assert handling_columns["original_menu_dish_id"]["nullable"] is False
        uniques = {item["name"] for item in inspector.get_unique_constraints("postpartum_conflict_handlings")}
        assert "uq_postpartum_conflict_handlings_item" in uniques
        foreign_keys = {item["name"]: item for item in inspector.get_foreign_keys("postpartum_conflict_handlings")}
        assert foreign_keys["fk_postpartum_conflict_handlings_group_slot"]["options"].get("ondelete") == "CASCADE"
        assert all(item["referred_table"] != "menu_dishes" for item in foreign_keys.values())
        with migrated_test_database.connect() as connection:
            definition = connection.scalar(text("""
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'ck_postpartum_conflict_handlings_meal'
            """))
            assert all(meal in definition for meal in (
                "breakfast", "morning_snack", "lunch",
                "afternoon_snack", "dinner", "evening_snack",
            ))
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260911_0020"
    finally:
        command.upgrade(config(), "head")
