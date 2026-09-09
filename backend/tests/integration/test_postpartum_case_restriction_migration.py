from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0016_to_0017_adds_case_restriction_association(migrated_test_database):
    command.downgrade(config(), "20260908_0016")
    try:
        command.upgrade(config(), "20260909_0017")
        inspector = inspect(migrated_test_database)
        table = "postpartum_case_restriction_groups"
        assert inspector.has_table(table)
        assert set(inspector.get_pk_constraint(table)["constrained_columns"]) == {
            "case_id", "restriction_group_id",
        }
        foreign_keys = {item["referred_table"]: item for item in inspector.get_foreign_keys(table)}
        assert foreign_keys["postpartum_cases"]["options"].get("ondelete") == "CASCADE"
        assert foreign_keys["postpartum_restriction_groups"]["options"].get("ondelete") == "RESTRICT"
        indexes = {item["name"] for item in inspector.get_indexes(table)}
        assert "ix_postpartum_case_restriction_groups_restriction_group_id" in indexes
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260909_0017"
    finally:
        command.upgrade(config(), "head")
