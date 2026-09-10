from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0018_to_0019_adds_multi_menu_sources_and_optional_meal_mapping(migrated_test_database):
    command.downgrade(config(), "20260909_0018")
    try:
        command.upgrade(config(), "20260909_0019")
        inspector = inspect(migrated_test_database)
        assert inspector.has_table("postpartum_menu_sources")
        assert inspector.has_table("postpartum_menu_meal_mappings")
        assert set(inspector.get_pk_constraint("postpartum_menu_meal_mappings")["constrained_columns"]) == {
            "menu_source_id", "postpartum_meal",
        }
        source_uniques = {item["name"] for item in inspector.get_unique_constraints("postpartum_menu_sources")}
        mapping_uniques = {item["name"] for item in inspector.get_unique_constraints("postpartum_menu_meal_mappings")}
        assert "uq_postpartum_menu_sources_menu_id" in source_uniques
        assert "scope" not in {item["name"] for item in inspector.get_columns("postpartum_menu_sources")}
        assert "uq_postpartum_menu_meal_mappings_source_meal_type" in mapping_uniques
        source_fks = {item["referred_table"]: item for item in inspector.get_foreign_keys("postpartum_menu_sources")}
        mapping_fks = {item["referred_table"]: item for item in inspector.get_foreign_keys("postpartum_menu_meal_mappings")}
        assert source_fks["menus"]["options"].get("ondelete") == "RESTRICT"
        assert mapping_fks["postpartum_menu_sources"]["options"].get("ondelete") == "CASCADE"
        assert mapping_fks["menu_meal_types"]["options"].get("ondelete") == "RESTRICT"
        with migrated_test_database.connect() as connection:
            definition = connection.scalar(text("""
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'ck_postpartum_menu_meal_mappings_meal'
            """))
            assert all(meal in definition for meal in (
                "breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner", "evening_snack",
            ))
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260909_0019"
    finally:
        command.upgrade(config(), "head")
