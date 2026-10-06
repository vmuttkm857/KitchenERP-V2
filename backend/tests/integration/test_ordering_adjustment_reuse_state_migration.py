from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root=Path(__file__).resolve().parents[2]
    value=Config(str(root/"alembic.ini"));value.set_main_option("script_location",str(root/"migrations"))
    return value


def test_0022_to_0023_adds_nullable_reuse_metadata(migrated_test_database):
    command.downgrade(config(),"20261006_0022")
    try:
        command.upgrade(config(),"20261006_0023")
        inspector=inspect(migrated_test_database)
        columns={column["name"]:column for column in inspector.get_columns("ordering_adjustment_sheets")}
        assert {"last_reuse_source_sheet_id","reuse_applied_at","reuse_applied_by"}.issubset(columns)
        assert all(columns[name]["nullable"] for name in ("last_reuse_source_sheet_id","reuse_applied_at","reuse_applied_by"))
        reuse_by_fk=next(item for item in inspector.get_foreign_keys("ordering_adjustment_sheets") if item["name"]=="fk_ordering_adjustment_sheets_reuse_applied_by_users")
        assert reuse_by_fk["referred_table"]=="users" and reuse_by_fk["options"].get("ondelete")=="RESTRICT"
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))=="20261006_0023"
    finally:
        command.upgrade(config(),"head")
