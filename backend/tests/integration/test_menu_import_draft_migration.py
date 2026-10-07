import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0023_to_0024_upgrade_downgrade_and_legacy_compatibility(migrated_test_database):
    command.downgrade(config(), "20261006_0023")
    legacy_user = uuid.uuid4()
    legacy_menu = uuid.uuid4()
    try:
        with migrated_test_database.begin() as connection:
            connection.execute(text(
                "INSERT INTO users(id,username,password_hash,display_name,role,is_active) "
                "VALUES (:id,'menu-import-migration-user','unused','Migration User','admin',true)"
            ), {"id": legacy_user})
            connection.execute(text(
                "INSERT INTO menus(id,name,start_date,end_date,is_active,created_by,updated_by) "
                "VALUES (:id,'Legacy Menu','2026-10-01','2026-10-07',true,:user_id,:user_id)"
            ), {"id": legacy_menu, "user_id": legacy_user})

        command.upgrade(config(), "20261007_0024")
        inspector = inspect(migrated_test_database)
        assert inspector.has_table("menu_import_batches")
        assert inspector.has_table("menu_import_lines")
        batch_columns = {item["name"] for item in inspector.get_columns("menu_import_batches")}
        line_columns = {item["name"] for item in inspector.get_columns("menu_import_lines")}
        assert {
            "status", "original_filename", "source_hash", "parser_version", "sheet_name",
            "review_required_count", "layout", "created_by", "updated_by",
        }.issubset(batch_columns)
        assert {
            "batch_id", "line_key", "menu_date", "meal_name", "column_name",
            "original_import_name", "normalized_import_name", "dish_id", "review_required",
            "resolution_status", "resolved_at", "resolved_by",
        }.issubset(line_columns)
        indexes = {item["name"]: item for item in inspector.get_indexes("menu_import_batches")}
        assert indexes["uq_menu_import_batches_active_source"]["unique"] is True
        line_uniques = {item["name"] for item in inspector.get_unique_constraints("menu_import_lines")}
        assert "uq_menu_import_lines_batch_line_key" in line_uniques
        line_fks = {item["name"]: item for item in inspector.get_foreign_keys("menu_import_lines")}
        assert line_fks["fk_menu_import_lines_batch"]["options"].get("ondelete") == "CASCADE"
        assert line_fks["fk_menu_import_lines_dish"]["options"].get("ondelete") == "SET NULL"
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM menus WHERE id=:id"), {"id": legacy_menu}) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261007_0024"

        command.downgrade(config(), "20261006_0023")
        inspector = inspect(migrated_test_database)
        assert not inspector.has_table("menu_import_lines")
        assert not inspector.has_table("menu_import_batches")
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM menus WHERE id=:id"), {"id": legacy_menu}) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261006_0023"
    finally:
        command.upgrade(config(), "head")
