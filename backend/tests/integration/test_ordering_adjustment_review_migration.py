from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root=Path(__file__).resolve().parents[2]
    value=Config(str(root/"alembic.ini"));value.set_main_option("script_location",str(root/"migrations"))
    return value


def test_0021_to_0022_adds_safe_review_required_default(migrated_test_database):
    command.downgrade(config(),"20261002_0021")
    try:
        command.upgrade(config(),"20261006_0022")
        columns={column["name"]:column for column in inspect(migrated_test_database).get_columns("ordering_adjustment_lines")}
        assert columns["review_required"]["nullable"] is False
        assert "false" in str(columns["review_required"]["default"]).lower()
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))=="20261006_0022"
    finally:
        command.upgrade(config(),"head")
