from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root=Path(__file__).resolve().parents[2];value=Config(str(root/"alembic.ini"));value.set_main_option("script_location",str(root/"migrations"));return value


def test_0020_to_0021_adds_ordering_adjustment_schema(migrated_test_database):
    command.downgrade(config(),"20260911_0020")
    try:
        command.upgrade(config(),"20261002_0021");inspector=inspect(migrated_test_database)
        assert inspector.has_table("ordering_adjustment_sheets") and inspector.has_table("ordering_adjustment_lines")
        sheet_uniques={item["name"] for item in inspector.get_unique_constraints("ordering_adjustment_sheets")}
        line_uniques={item["name"] for item in inspector.get_unique_constraints("ordering_adjustment_lines")}
        snapshot_columns={item["name"] for item in inspector.get_columns("requirement_snapshots")}
        sheet_columns={item["name"] for item in inspector.get_columns("ordering_adjustment_sheets")}
        line_columns={item["name"] for item in inspector.get_columns("ordering_adjustment_lines")}
        snapshot_indexes={item["name"] for item in inspector.get_indexes("requirement_snapshots")}
        sheet_indexes={item["name"] for item in inspector.get_indexes("ordering_adjustment_sheets")}
        assert "snapshot_kind" in snapshot_columns
        assert "criteria_fingerprint" in sheet_columns
        assert "uq_requirement_snapshots_standard_content" in snapshot_indexes
        assert "uq_ordering_adjustment_sheets_active_source" in sheet_indexes
        assert "uq_ordering_adjustment_sheets_snapshot" in sheet_uniques
        assert {"uq_ordering_adjustment_lines_source","uq_ordering_adjustment_lines_key"}.issubset(line_uniques)
        assert {
            "meal_type_sort_order_snapshot","menu_meal_type_column_sort_order_snapshot",
            "menu_dish_sort_order_snapshot","dish_ingredient_sort_order_snapshot",
        }.issubset(line_columns)
        line_fks=inspector.get_foreign_keys("ordering_adjustment_lines")
        assert all(item["referred_table"] not in {"menu_dishes","dish_ingredients"} for item in line_fks)
        with migrated_test_database.connect() as connection:assert connection.scalar(text("SELECT version_num FROM alembic_version"))=="20261002_0021"
    finally:command.upgrade(config(),"head")
