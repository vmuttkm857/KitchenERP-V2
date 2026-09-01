from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config() -> Config:
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0008_to_0009_creates_append_only_audit_schema(migrated_test_database) -> None:
    command.downgrade(config(), "20260830_0008")
    try:
        command.upgrade(config(), "20260831_0009")
        inspector = inspect(migrated_test_database)
        columns = {column["name"] for column in inspector.get_columns("audit_logs")}
        assert {"actor_user_id", "actor_username", "actor_display_name", "action", "entity_type",
                "before_data", "after_data", "metadata", "request_id", "ip_address", "created_at"} <= columns
        foreign_keys = inspector.get_foreign_keys("audit_logs")
        assert foreign_keys[0]["referred_table"] == "users"
        assert foreign_keys[0]["options"].get("ondelete") == "RESTRICT"
        assert {index["name"] for index in inspector.get_indexes("audit_logs")} >= {
            "ix_audit_logs_created_at", "ix_audit_logs_actor_created",
            "ix_audit_logs_action_created", "ix_audit_logs_entity_created",
        }
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260831_0009"
    finally:
        command.upgrade(config(), "head")


def test_fresh_postgresql_base_to_head_includes_audit_logs(migrated_test_database) -> None:
    command.downgrade(config(), "base")
    try:
        command.upgrade(config(), "head")
        assert inspect(migrated_test_database).has_table("audit_logs")
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260901_0012"
            for table in ("nutrition_foods", "nutrition_nutrients", "nutrition_food_values", "nutrition_import_batches"):
                assert inspect(migrated_test_database).has_table(table)
    finally:
        command.upgrade(config(), "head")


def test_0010_to_0011_adds_nutrition_unit_conversions(migrated_test_database) -> None:
    command.downgrade(config(), "20260901_0010")
    try:
        assert not inspect(migrated_test_database).has_table("ingredient_nutrition_unit_conversions")
        command.upgrade(config(), "20260901_0011")
        inspector = inspect(migrated_test_database)
        assert inspector.has_table("ingredient_nutrition_unit_conversions")
        columns = {column["name"] for column in inspector.get_columns("ingredient_nutrition_unit_conversions")}
        assert {"ingredient_id", "unit", "grams_per_unit", "created_by", "updated_by", "created_at", "updated_at"} <= columns
        unique = {constraint["name"] for constraint in inspector.get_unique_constraints("ingredient_nutrition_unit_conversions")}
        assert "uq_ingredient_nutrition_unit_conversions_ingredient_unit" in unique
        foreign_keys = {tuple(key["constrained_columns"]): key for key in inspector.get_foreign_keys("ingredient_nutrition_unit_conversions")}
        assert foreign_keys[("ingredient_id",)]["options"].get("ondelete") == "CASCADE"
        assert foreign_keys[("created_by",)]["options"].get("ondelete") == "RESTRICT"
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260901_0011"
    finally:
        command.upgrade(config(), "head")


def test_0011_to_0012_adds_standard_recipe_card_schema(migrated_test_database) -> None:
    command.downgrade(config(), "20260901_0011")
    try:
        command.upgrade(config(), "20260901_0012")
        inspector = inspect(migrated_test_database)
        for table in ("dish_production_profiles", "production_batch_versions", "production_batch_ingredients", "production_process_steps"):
            assert inspector.has_table(table)
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260901_0012"
    finally:
        command.upgrade(config(), "head")
