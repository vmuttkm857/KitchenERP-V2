"""Real PostgreSQL DDL; existing guards require a separately approved migration DB."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_upgrade_preserves_categories_and_null_color_downgrade(migrated_test_database):
    engine = migrated_test_database
    command.downgrade(config(), "20261029_0028")
    actor, category = uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,username,password_hash,display_name,role) VALUES (:id,:name,'test-only-not-loginable','Color migration','admin')"), {"id":actor,"name":"color-" + actor.hex})
        conn.execute(text("INSERT INTO dish_categories (id,name,sort_order,created_by,updated_by) VALUES (:id,'Migration category',7,:actor,:actor)"), {"id":category,"actor":actor})
        before = conn.execute(text("SELECT id,name,sort_order,is_active,created_at,updated_at,created_by,updated_by FROM dish_categories WHERE id=:id"), {"id":category}).one()
    command.upgrade(config(), "20261103_0029")
    with engine.connect() as conn:
        after = conn.execute(text("SELECT id,name,sort_order,is_active,created_at,updated_at,created_by,updated_by FROM dish_categories WHERE id=:id"), {"id":category}).one()
        assert conn.scalar(text("SELECT background_color FROM dish_categories WHERE id=:id"), {"id":category}) is None
    assert before == after
    for table in ("categories", "menu_categories"):
        assert "background_color" not in {column["name"] for column in inspect(engine).get_columns(table)}
    command.downgrade(config(), "20261029_0028")
    assert "background_color" not in {column["name"] for column in inspect(engine).get_columns("dish_categories")}
    command.upgrade(config(), "head")


def test_check_constraint_and_downgrade_refuse_color_loss(migrated_test_database):
    engine = migrated_test_database
    actor, category = uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,username,password_hash,display_name,role) VALUES (:id,:name,'test-only-not-loginable','Color migration','admin')"), {"id":actor,"name":"color-" + actor.hex})
        conn.execute(text("INSERT INTO dish_categories (id,name,background_color,created_by,updated_by) VALUES (:id,'Color constraint','#BBDEFB',:actor,:actor)"), {"id":category,"actor":actor})
    with pytest.raises(IntegrityError) as caught:
        with engine.begin() as conn:
            conn.execute(text("UPDATE dish_categories SET background_color='invalid' WHERE id=:id"), {"id":category})
    assert caught.value.orig.diag.constraint_name == "ck_dish_categories_background_color"
    with pytest.raises(DBAPIError, match="DISH_CATEGORY_COLORS_PREVENT_DOWNGRADE"):
        command.downgrade(config(), "20261029_0028")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20261103_0029"
        assert conn.scalar(text("SELECT background_color FROM dish_categories WHERE id=:id"), {"id":category}) == "#BBDEFB"
