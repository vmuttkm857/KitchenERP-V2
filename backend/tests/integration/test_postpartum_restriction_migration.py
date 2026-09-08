from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0015_to_0016_adds_postpartum_restriction_schema(migrated_test_database):
    command.downgrade(config(), "20260908_0015")
    try:
        command.upgrade(config(), "20260908_0016")
        inspector = inspect(migrated_test_database)
        assert inspector.has_table("postpartum_restriction_groups")
        assert inspector.has_table("postpartum_restriction_group_ingredients")
        assert inspector.has_table("postpartum_restriction_group_dishes")
        groups = {column["name"]: column for column in inspector.get_columns("postpartum_restriction_groups")}
        assert groups["name"]["nullable"] is False
        assert groups["color"]["type"].length == 7
        assert groups["is_active"]["nullable"] is False
        group_indexes = {item["name"] for item in inspector.get_indexes("postpartum_restriction_groups")}
        assert "uq_postpartum_restriction_groups_name_normalized" in group_indexes
        assert "ix_postpartum_restriction_groups_is_active" in group_indexes
        ingredient_pk = inspector.get_pk_constraint("postpartum_restriction_group_ingredients")["constrained_columns"]
        dish_pk = inspector.get_pk_constraint("postpartum_restriction_group_dishes")["constrained_columns"]
        assert set(ingredient_pk) == {"restriction_group_id", "ingredient_id"}
        assert set(dish_pk) == {"restriction_group_id", "dish_id"}
        for table, target in (("postpartum_restriction_group_ingredients", "ingredients"), ("postpartum_restriction_group_dishes", "dishes")):
            foreign_keys = {item["referred_table"]: item for item in inspector.get_foreign_keys(table)}
            assert foreign_keys["postpartum_restriction_groups"]["options"].get("ondelete") == "CASCADE"
            assert foreign_keys[target]["options"].get("ondelete") == "RESTRICT"
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260908_0016"
    finally:
        command.upgrade(config(), "head")
