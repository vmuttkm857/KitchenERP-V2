"""Database-free contract and service checks; not PostgreSQL integration tests."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock
from pathlib import Path
from io import StringIO
import importlib.util

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.routes import categories as routes
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.exceptions import InvalidAccessTokenError
from app.api.dependencies import get_db_session
from app.domains.categories.models import DishCategory, IngredientCategory, MenuCategory
from app.domains.categories.schemas import CategoryCreate, CategoryUpdate, CategoryList
from app.domains.categories.service import CategoryService
from app.domains.categories.exceptions import InvalidCategoryColorError
from app.domains.menus.service import MenuService
from app.domains.menus.fingerprint import editor_fingerprint, slot_fingerprint


@pytest.mark.parametrize("schema", [CategoryCreate, CategoryUpdate])
@pytest.mark.parametrize("value", ["red", "#abc", "#12345678", "123456", "#GG0000", "#123456\n", "url(secret)"])
def test_invalid_color_is_rejected(schema, value):
    with pytest.raises(ValidationError):
        schema(name="主菜", background_color=value)


def service():
    value = CategoryService(Mock())
    value.repository = Mock()
    value.repository.name_exists.return_value = False
    value.repository.model_for.return_value = DishCategory
    value.audit = Mock()
    return value


def test_create_update_clear_and_audit_preserve_other_fields():
    value = service()
    actor = uuid4()
    category = value.create("dish", CategoryCreate(name="主菜", background_color="#dcedc8", sort_order=7), actor)
    category.is_active = True
    value.repository.get.return_value = category
    assert category.background_color == "#DCEDC8"
    assert value.audit.record.call_args.kwargs["after_data"]["background_color"] == "#DCEDC8"
    value.update("dish", category.id, CategoryUpdate(name="改名", sort_order=9), actor)
    assert category.background_color == "#DCEDC8"
    value.update("dish", category.id, CategoryUpdate(background_color="#bbdefb"), actor)
    audit = value.audit.record.call_args.kwargs
    assert audit["before_data"]["background_color"] == "#DCEDC8"
    assert audit["after_data"]["background_color"] == "#BBDEFB"
    value.set_active("dish", category.id, False, actor)
    assert category.background_color == "#BBDEFB"
    value.update("dish", category.id, CategoryUpdate(background_color=None), actor)
    assert category.background_color is None
    assert (category.name, category.sort_order, category.is_active, category.created_by) == ("改名", 9, False, actor)


def test_legacy_create_defaults_to_null():
    value = service()
    assert value.create("dish", CategoryCreate(name="舊客戶端"), uuid4()).background_color is None


@pytest.mark.parametrize("kind,model", [("ingredient", IngredientCategory), ("menu", MenuCategory)])
def test_color_does_not_extend_other_category_tables_or_writes(kind, model):
    assert "background_color" not in model.__table__.columns
    value = service()
    for data in (CategoryCreate(name="測試", background_color=None), CategoryUpdate(background_color="#BBDEFB")):
        with pytest.raises(InvalidCategoryColorError):
            (value.create(kind, data, uuid4()) if isinstance(data, CategoryCreate)
             else value.update(kind, uuid4(), data, uuid4()))
    value.session.commit.assert_not_called()


def public_record(**extra):
    actor = uuid4()
    return SimpleNamespace(id=uuid4(), name="分類", sort_order=0, is_active=True,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        created_by=actor, updated_by=actor, **extra)


def test_response_union_retains_color_and_keeps_other_categories_original_shape():
    dish = routes.category_public("dish", public_record(background_color=None))
    other = routes.category_public("menu", public_record())
    result = CategoryList(items=[dish, other], pagination={"page":1,"page_size":100,"total":2}).model_dump()
    assert result["items"][0]["background_color"] is None
    assert "background_color" not in result["items"][1]


def test_http_contract_validation_and_existing_authorization(monkeypatch):
    # Exercise FastAPI parsing/serialization; persistence is covered separately in PG tests.
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db_session] = lambda: Mock()
    value = service()
    record = public_record(background_color="#BBDEFB")
    value.repository.get.return_value = record
    value.repository.list.return_value = ([record], 1)
    monkeypatch.setattr(routes, "service", lambda _: value)
    with TestClient(app) as client:
        assert client.patch(f"/categories/dish/{record.id}", json={"background_color":"invalid"}).status_code == 422
        colored = client.patch(f"/categories/dish/{record.id}", json={"background_color":"#dcedc8"})
        assert colored.status_code == 200 and colored.json()["background_color"] == "#DCEDC8"
        response = client.patch(f"/categories/dish/{record.id}", json={"background_color":None})
        assert response.status_code == 200 and response.json()["background_color"] is None
        assert client.get("/categories/dish").json()["items"][0]["background_color"] is None
        assert client.patch(f"/categories/menu/{record.id}", json={"background_color":"#BBDEFB"}).status_code == 422
        app.dependency_overrides.pop(get_current_user)
        # This isolated router app has no main.py exception handlers; authentication
        # must still reject the request before any category service mutation.
        before = value.session.commit.call_count
        with pytest.raises(InvalidAccessTokenError):
            client.patch(f"/categories/dish/{record.id}", json={"background_color":"#BBDEFB"})
        assert value.session.commit.call_count == before


def aggregate_fixture():
    menu, meal, dish, category, day, menu_dish, actor = [uuid4() for _ in range(7)]
    menu_date = date(2026,11,9)
    repository = Mock()
    repository.menu_view.return_value = {"id":menu,"start_date":menu_date,"end_date":menu_date,"is_active":True}
    repository.meal_types.return_value = [SimpleNamespace(id=meal,name="午餐",sort_order=1,is_active=True)]
    repository.menu_columns.return_value = []
    repository.aggregate_rows.return_value = [{"menu_day_id":day,"menu_date":menu_date,"menu_meal_type_id":meal,
        "slot_notes":None,"menu_dish_id":menu_dish,"dish_id":dish,"menu_meal_type_column_id":None,
        "dish_code":"D1","dish_name":"測試菜色","dish_category_name":"主菜","dish_category_id":category,
        "diner_count":20,"notes":None,"sort_order":1,"created_by":actor,"updated_by":actor}]
    value = MenuService(Mock())
    value.repository = repository
    value._meal = Mock()
    return value, menu, meal, dish, category, menu_date


def test_display_map_is_outside_slot_and_legacy_fingerprints_are_identical():
    value, menu, meal, dish, category, menu_date = aggregate_fixture()
    result = value.aggregate(menu)
    legacy = {key:item for key,item in result.items() if key != "dish_category_ids"}
    assert result["dish_category_ids"] == {str(dish):category}
    assert "dish_category_id" not in result["slots"][0]["dishes"][0]
    assert result["editor_fingerprint"] == editor_fingerprint(legacy)
    assert slot_fingerprint(result,menu_date,meal) == slot_fingerprint(legacy,menu_date,meal)
    detail = value.meal_slot(menu,meal,menu_date)
    assert detail["dish_category_ids"] == {str(dish):category}
    assert detail["slot_fingerprint"] == slot_fingerprint(legacy,menu_date,meal)
    # Display metadata (including any refreshed display color) is never business content.
    result["dish_category_ids"] = {str(dish):None}
    result["category_colors"] = {str(category):"#BBDEFB"}
    assert editor_fingerprint(result) == editor_fingerprint(legacy)
    assert slot_fingerprint(result,menu_date,meal) == slot_fingerprint(legacy,menu_date,meal)


def test_migration_offline_sql_is_additive_and_downgrade_refuses_color_loss():
    path = Path(__file__).resolve().parents[2]/"migrations/versions/20261103_0029_dish_category_background_color.py"
    spec = importlib.util.spec_from_file_location("color_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    buffer = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql":True,"output_buffer":buffer})
    with Operations.context(context):
        migration.upgrade()
        upgrade = buffer.getvalue()
        migration.downgrade()
    assert "ALTER TABLE dish_categories ADD COLUMN background_color VARCHAR(7)" in upgrade
    assert "ck_dish_categories_background_color" in upgrade
    assert "UPDATE " not in upgrade and "DROP " not in upgrade
    assert "ALTER TABLE categories " not in upgrade and "ALTER TABLE menu_categories " not in upgrade
    sql = buffer.getvalue()
    assert sql.index("DISH_CATEGORY_COLORS_PREVENT_DOWNGRADE") < sql.index("DROP COLUMN background_color")
    assert migration.down_revision == "20261029_0028"
