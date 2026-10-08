from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root=Path(__file__).resolve().parents[2];value=Config(str(root/"alembic.ini"));value.set_main_option("script_location",str(root/"migrations"));return value


def test_0026_to_0027_adds_persisted_adjusted_unit(migrated_test_database):
    command.downgrade(config(),"20261007_0026")
    try:
        command.upgrade(config(),"20261008_0027")
        inspector=inspect(migrated_test_database)
        columns={item["name"] for item in inspector.get_columns("ordering_adjustment_lines")}
        checks={item["name"] for item in inspector.get_check_constraints("ordering_adjustment_lines")}
        assert "adjusted_unit" in columns
        assert "ck_ordering_adjustment_lines_adjusted_pair" in checks
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))=="20261008_0027"
    finally:command.upgrade(config(),"head")
