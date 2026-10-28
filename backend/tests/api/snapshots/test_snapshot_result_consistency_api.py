"""H07 PostgreSQL workflows, subject to the existing disposable-database guard."""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.domains.ingredients.models import Ingredient
from app.domains.menus.models import MenuDish
from app.domains.order_adjustments.models import OrderingAdjustmentLine
from app.domains.recipes.models import DishIngredient
from app.domains.snapshots.models import RequirementSnapshot
from tests.api.order_adjustments.test_order_adjustments_api import create_sheet
from tests.api.requirements.test_requirements_api import auth, fixture
from tests.snapshot_requests import save_snapshot


@pytest.mark.parametrize("change", ["recipe", "menu", "manual", "price"])
def test_changed_content_returns_409_without_creating_a_snapshot(client, db_session, change):
    headers = auth(client, db_session)
    menu, _, _, _, _ = fixture(client, headers)
    criteria = {"menu_ids": [menu["id"]]}
    if change == "manual":
        sheet = create_sheet(client, headers, menu).json()
        criteria.update(ordering_adjustment_sheet_ids=[sheet["id"]], selected_dates=["2026-09-01"])
    viewed = client.post("/api/v1/requirements/calculate", headers=headers, json=criteria)
    assert viewed.status_code == 200, viewed.text
    before = db_session.scalar(select(func.count()).select_from(RequirementSnapshot))
    if change == "recipe":
        row = db_session.scalar(select(DishIngredient))
        row.quantity += Decimal("1")
    elif change == "menu":
        row = db_session.scalar(select(MenuDish))
        row.diner_count += 1
    elif change == "manual":
        row = db_session.get(OrderingAdjustmentLine, UUID(sheet["lines"][0]["id"]))
        row.adjusted_quantity, row.adjusted_unit = Decimal("123"), row.system_unit
    else:
        row = db_session.scalar(select(Ingredient).where(Ingredient.code == "REQ-I1"))
        row.current_price += Decimal("1")
    db_session.commit()
    response = client.post("/api/v1/requirement-snapshots", headers=headers, json={
        "criteria": criteria, "expected_result_fingerprint": viewed.json()["result_fingerprint"],
    })
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "SNAPSHOT_RESULT_CHANGED"
    assert db_session.scalar(select(func.count()).select_from(RequirementSnapshot)) == before


def test_unchanged_result_is_saved_and_old_clients_cannot_bypass_validation(client, db_session):
    headers = auth(client, db_session)
    menu, *_ = fixture(client, headers)
    criteria = {"menu_ids": [menu["id"]]}
    for extra in ({}, {"expected_result_fingerprint": "invalid"}, {"expected_result_fingerprint": None}):
        response = client.post("/api/v1/requirement-snapshots", headers=headers, json={"criteria": criteria, **extra})
        assert response.status_code == 422
    response = save_snapshot(client, headers, criteria)
    assert response.status_code == 201, response.text
