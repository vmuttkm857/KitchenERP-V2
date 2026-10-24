import copy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.domains.order_adjustments.repository import OrderingAdjustmentRepository
from app.domains.order_adjustments.models import OrderingAdjustmentSheet
from app.domains.purchases.models import PurchaseBatch
from app.domains.snapshots.models import RequirementSnapshot, RequirementSnapshotItem
from tests.api.order_adjustments.test_order_adjustments_api import create_sheet
from tests.api.requirements.test_requirements_api import auth, fixture


def setup(client, db_session):
    headers = auth(client, db_session)
    menu, meals, dishes, ingredients, _ = fixture(client, headers)
    sheet = create_sheet(client, headers, menu).json()
    return headers, menu, meals, dishes, ingredients, sheet


def slot_url(menu, meal, day="2026-09-01"):
    return f"/api/v1/menus/{menu['id']}/meal-slots/{meal['id']}/{day}"


def payload(client, headers, url, sheet):
    slot = client.get(url, headers=headers).json()
    return {"expected_slot_fingerprint": slot["slot_fingerprint"], "menu_day_id": slot["menu_day_id"],
            "notes": slot["notes"], "dishes": slot["dishes"],
            "ordering_adjustment_context": {"sheet_id": sheet["id"], "lock_version": sheet["lock_version"]}}


def test_inline_edit_saves_source_only_preserves_adjustments_and_requires_one_explicit_sync(client, db_session):
    headers, menu, meals, _, _, sheet = setup(client, db_session)
    line = sheet["lines"][0]
    sheet = client.patch(f"/api/v1/order-adjustments/{sheet['id']}/lines", headers=headers,
        json={"lock_version": sheet["lock_version"], "lines": [{"id": line["id"], "adjusted_quantity": "25", "adjusted_unit": "kg"}]}).json()
    standard = client.post("/api/v1/requirement-snapshots", headers=headers,
        json={"criteria": {**sheet["criteria"], "ordering_adjustment_sheet_ids": [sheet["id"]]}}).json()
    standard = client.get(f"/api/v1/requirement-snapshots/{standard['id']}", headers=headers).json()
    snapshot_state = {item.id: (item.requirement_quantity, item.adjusted_quantity)
        for item in db_session.scalars(select(RequirementSnapshotItem))}
    before_lines = copy.deepcopy(sheet["lines"])
    for meal in meals[:2]:
        url = slot_url(menu, meal)
        body = payload(client, headers, url, sheet)
        body["dishes"][0]["diner_count"] += 5
        response = client.put(url, headers=headers, json=body)
        assert response.status_code == 200, response.text
        current = client.get(f"/api/v1/order-adjustments/{sheet['id']}", headers=headers).json()
        assert current["stale"] is True and current["lock_version"] == sheet["lock_version"]
        assert [(v["id"], v["adjusted_quantity"], v["adjusted_unit"]) for v in current["lines"]] == [
            (v["id"], v["adjusted_quantity"], v["adjusted_unit"]) for v in before_lines]
    stale_patch = client.patch(f"/api/v1/order-adjustments/{sheet['id']}/lines", headers=headers,
        json={"lock_version": sheet["lock_version"], "lines": [{"id": line["id"], "adjusted_quantity": "99"}]})
    assert stale_patch.status_code == 409 and stale_patch.json()["detail"]["code"] == "ADJUSTMENT_STALE"
    criteria = {**sheet["criteria"], "ordering_adjustment_sheet_ids": [sheet["id"]]}
    assert client.post("/api/v1/requirements/calculate", headers=headers, json=criteria).status_code == 409
    preview = client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview", headers=headers,
        json={"lock_version": sheet["lock_version"]}).json()
    synced = client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync", headers=headers, json={
        "lock_version": preview["lock_version"], "expected_source_fingerprint": preview["preview_source_fingerprint"],
        "accepted_removed_source_line_keys": [], "reset_adjustment_line_ids": []})
    assert synced.status_code == 200, synced.text
    assert synced.json()["stale"] is False
    kept = next(v for v in synced.json()["lines"] if v["id"] == line["id"])
    assert Decimal(kept["adjusted_quantity"]) == 25 and kept["adjusted_unit"] == "kg"
    assert client.post("/api/v1/requirements/calculate", headers=headers, json=criteria).status_code == 200
    assert client.get(f"/api/v1/requirement-snapshots/{standard['id']}", headers=headers).json() == standard
    db_session.expire_all()
    # Standard snapshots remain historical; the only baseline update is the explicit sync.
    standard_ids = {v.id for v in db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id == standard["id"]))}
    assert all((v.requirement_quantity, v.adjusted_quantity) == snapshot_state[v.id]
        for v in db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.id.in_(standard_ids))))
    assert db_session.scalar(select(func.count()).select_from(PurchaseBatch)) == 0
    assert db_session.scalar(select(func.count()).select_from(RequirementSnapshot)) == 2


@pytest.mark.parametrize("state", ["confirmed", "cancelled", "version", "purchase", "scope", "date", "unauthorized"])
def test_inline_save_context_rejects_locked_invalid_and_out_of_scope_without_writes(client, db_session, state):
    headers, menu, meals, _, _, sheet = setup(client, db_session)
    url = slot_url(menu, meals[0], "2026-09-02" if state == "date" else "2026-09-01")
    body = payload(client, headers, url, sheet)
    before = client.get(url, headers=headers).json()
    if state in {"confirmed", "cancelled", "purchase"}:
        if state == "cancelled":
            current = client.post(f"/api/v1/order-adjustments/{sheet['id']}/cancel", headers=headers, json={"lock_version": sheet["lock_version"]}).json()
        else:
            current = client.post(f"/api/v1/order-adjustments/{sheet['id']}/confirm", headers=headers, json={"lock_version": sheet["lock_version"]}).json()
        body["ordering_adjustment_context"]["lock_version"] = current["lock_version"]
        if state == "purchase":
            purchase = client.post("/api/v1/purchases", headers=headers, json={"snapshot_id": sheet["baseline_snapshot_id"]})
            assert purchase.status_code == 201, purchase.text
            # Legacy/inconsistent draft with a purchase must also fail closed.
            db_session.expire_all(); stored = db_session.get(OrderingAdjustmentSheet, sheet["id"])
            stored.status = "draft"; db_session.commit()
            assert client.get(f"/api/v1/order-adjustments/{sheet['id']}", headers=headers).json()["purchase_locked"] is True
    elif state == "version": body["ordering_adjustment_context"]["lock_version"] += 1
    elif state == "scope":
        other = client.post("/api/v1/menus", headers=headers, json={"name": "其他菜單", "start_date": "2026-09-01", "end_date": "2026-09-03", "category_id": menu["category_id"]}).json()
        other_meal = client.post(f"/api/v1/menus/{other['id']}/meal-types", headers=headers, json={"name": "午餐", "sort_order": 1}).json()
        url = slot_url(other, other_meal); body = payload(client, headers, url, sheet); before = client.get(url, headers=headers).json()
    body["notes"] = "不得寫入"
    response = client.put(url, headers={} if state == "unauthorized" else headers, json=body)
    expected = {"unauthorized": 401, "scope": 403, "date": 403}.get(state, 409)
    assert response.status_code == expected, response.text
    if state == "purchase": assert response.json()["detail"]["code"] == "SNAPSHOT_LOCKED"
    assert client.get(url, headers=headers).json() == before


def test_inline_empty_recipe_meal_uses_real_slot_and_independent_meal_versions(client, db_session):
    headers, menu, meals, _, _, sheet = setup(client, db_session)
    empty = client.post(f"/api/v1/menus/{menu['id']}/meal-types", headers=headers, json={"name": "無食材餐別", "sort_order": 4}).json()
    urls = [slot_url(menu, empty), slot_url(menu, meals[0])]
    bodies = [payload(client, headers, url, sheet) for url in urls]
    bodies[0]["notes"] = "空餐次可編輯"
    bodies[1]["notes"] = "不同餐次不被覆蓋"
    for url, body in zip(urls, bodies): assert client.put(url, headers=headers, json=body).status_code == 200
    assert client.put(urls[0], headers=headers, json=bodies[0]).status_code == 409


def test_inline_edit_and_confirm_share_the_adjustment_row_lock(client, db_session, monkeypatch):
    headers, menu, meals, _, _, sheet = setup(client, db_session)
    url = slot_url(menu, meals[0]); body = payload(client, headers, url, sheet)
    body["dishes"][0]["diner_count"] += 2
    barrier = Barrier(2, timeout=10); original = OrderingAdjustmentRepository.sheet
    def simultaneous(repository, sheet_id, for_update=False):
        if for_update: barrier.wait()
        return original(repository, sheet_id, for_update)
    monkeypatch.setattr(OrderingAdjustmentRepository, "sheet", simultaneous)
    with ThreadPoolExecutor(max_workers=2) as pool:
        edit = pool.submit(client.put, url, headers=headers, json=body)
        confirm = pool.submit(client.post, f"/api/v1/order-adjustments/{sheet['id']}/confirm", headers=headers, json={"lock_version": sheet["lock_version"]})
        responses = [edit.result(timeout=20), confirm.result(timeout=20)]
    assert sorted(v.status_code for v in responses) == [200, 409], [v.text for v in responses]


@pytest.mark.parametrize("same_meal", [True, False])
def test_two_inline_tabs_preserve_slot_versions_under_real_concurrency(client, db_session, monkeypatch, same_meal):
    headers, menu, meals, _, _, sheet = setup(client, db_session)
    urls = [slot_url(menu, meals[0]), slot_url(menu, meals[0 if same_meal else 1])]
    bodies = [payload(client, headers, url, sheet) for url in urls]
    for i, body in enumerate(bodies): body["notes"] = f"inline-tab-{i}"
    barrier = Barrier(2, timeout=10); original = OrderingAdjustmentRepository.sheet
    def simultaneous(repository, sheet_id, for_update=False):
        if for_update: barrier.wait()
        return original(repository, sheet_id, for_update)
    monkeypatch.setattr(OrderingAdjustmentRepository, "sheet", simultaneous)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.put, url, headers=headers, json=body) for url, body in zip(urls, bodies)]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(v.status_code for v in responses) == ([200, 409] if same_meal else [200, 200])
    if not same_meal:
        assert [client.get(url, headers=headers).json()["notes"] for url in urls] == ["inline-tab-0", "inline-tab-1"]
