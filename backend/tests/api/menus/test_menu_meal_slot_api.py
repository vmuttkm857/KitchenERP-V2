import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.domains.audit.models import AuditLog
from app.domains.audit.service import AuditLogService
from app.domains.menus.models import MenuDay, MenuDish
from app.domains.menus.repository import MenuRepository
from app.domains.menus.service import MenuService
from tests.api.menus.test_menus_api import auth, foundations, meals, menu
from tests.menu_editor import save_editor


def _setup(client, db_session):
    headers, _ = auth(client, db_session)
    category, dishes = foundations(client, headers, 4)
    value = menu(client, headers, category["id"])
    breakfast, lunch = meals(client, headers, value["id"], ("早餐", "午餐"))
    slots = [{"menu_date": day, "menu_meal_type_id": meal["id"], "notes": f"{day}-{meal['name']}",
              "dishes": [{"dish_id": dish["id"], "diner_count": 20 + index,
                          "sort_order": index + 1, "notes": f"備註-{index}"}
                         for index, dish in enumerate(dishes[:2])]}
             for day in ("2026-09-01", "2026-09-02") for meal in (breakfast, lunch)]
    response = save_editor(client, f"/api/v1/menus/{value['id']}/editor", headers=headers, json={"slots": slots})
    assert response.status_code == 200, response.text
    return headers, value, breakfast, lunch, dishes


def _url(value, meal, day="2026-09-01"):
    return f"/api/v1/menus/{value['id']}/meal-slots/{meal['id']}/{day}"


def _payload(slot, **changes):
    return {"expected_slot_fingerprint": slot["slot_fingerprint"], "menu_day_id": slot["menu_day_id"],
            "notes": slot["notes"], "dishes": copy.deepcopy(slot["dishes"]), **changes}


def _editor(client, headers, value):
    response = client.get(f"/api/v1/menus/{value['id']}/editor", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_save_only_target_slot_preserves_ids_and_every_other_row(client, db_session):
    headers, value, breakfast, _, dishes = _setup(client, db_session)
    before = _editor(client, headers, value)
    slot = client.get(_url(value, breakfast), headers=headers).json()
    # Include DB audit timestamps: an untouched meal must not even be rewritten.
    other_days = list(db_session.scalars(select(MenuDay).where(
        MenuDay.menu_id == value["id"], MenuDay.id != slot["menu_day_id"])))
    other_ids = [row.id for row in other_days]
    others = list(db_session.scalars(select(MenuDish).where(MenuDish.menu_day_id.in_(other_ids))))
    other_state = {row.id: {c.name: getattr(row, c.name) for c in row.__table__.columns}
                   for row in [*other_days, *others]}
    payload = _payload(slot, notes="新的本餐備註")
    kept = payload["dishes"][1]
    kept.update(diner_count=75, notes="保留菜色的新備註", sort_order=5)
    payload["dishes"] = [kept, {"dish_id": dishes[2]["id"], "diner_count": 9,
                               "notes": "新增菜色", "sort_order": 1}]
    response = client.put(_url(value, breakfast), headers=headers, json=payload)
    assert response.status_code == 200, response.text
    after = response.json()
    changed = next(item for item in after["slots"] if item["menu_day_id"] == slot["menu_day_id"])
    assert changed["notes"] == "新的本餐備註"
    assert [item["dish_id"] for item in changed["dishes"]] == [dishes[2]["id"], dishes[1]["id"]]
    assert [item["sort_order"] for item in changed["dishes"]] == [1, 2]
    assert changed["dishes"][1]["id"] == kept["id"]
    assert changed["dishes"][1]["diner_count"] == 75
    assert changed["dishes"][1]["notes"] == "保留菜色的新備註"
    assert slot["dishes"][0]["id"] not in {item["id"] for item in changed["dishes"]}
    assert [item for item in after["slots"] if item["menu_day_id"] != slot["menu_day_id"]] == [
        item for item in before["slots"] if item["menu_day_id"] != slot["menu_day_id"]]
    db_session.expire_all()
    assert {row.id: {c.name: getattr(row, c.name) for c in row.__table__.columns}
            for row in [*other_days, *others]} == other_state
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "menu_meal_slot_save"))
    assert log is not None and str(log.entity_id) == value["id"]


def test_columns_can_swap_and_be_reused_after_removal_without_unique_collision(client, db_session):
    headers, value, breakfast, _, dishes = _setup(client, db_session)
    columns = [client.post(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns",
                           headers=headers, json={"name": name, "sort_order": index + 1}).json()
               for index, name in enumerate(("主菜", "副菜"))]
    slot = client.get(_url(value, breakfast), headers=headers).json()
    payload = _payload(slot)
    for index, item in enumerate(payload["dishes"]):
        item["menu_meal_type_column_id"] = columns[index]["id"]
    assert client.put(_url(value, breakfast), headers=headers, json=payload).status_code == 200
    slot = client.get(_url(value, breakfast), headers=headers).json()
    payload = _payload(slot)
    payload["dishes"][0]["menu_meal_type_column_id"] = columns[1]["id"]
    payload["dishes"][1]["menu_meal_type_column_id"] = columns[0]["id"]
    response = client.put(_url(value, breakfast), headers=headers, json=payload)
    assert response.status_code == 200, response.text
    slot = client.get(_url(value, breakfast), headers=headers).json()
    assert [item["dish_id"] for item in slot["dishes"]] == [dishes[1]["id"], dishes[0]["id"]]
    old_id = slot["dishes"][0]["id"]
    payload = _payload(slot)
    # Remove and re-add the same Dish and occupied column as a new MenuDish.
    payload["dishes"][0].pop("id")
    response = client.put(_url(value, breakfast), headers=headers, json=payload)
    assert response.status_code == 200, response.text
    current = client.get(_url(value, breakfast), headers=headers).json()
    assert current["dishes"][0]["id"] != old_id
    assert current["dishes"][0]["menu_meal_type_column_id"] == columns[0]["id"]


def test_same_slot_stale_or_missing_version_rejected_and_inputs_not_overwritten(client, db_session):
    headers, value, breakfast, _, _ = _setup(client, db_session)
    slot = client.get(_url(value, breakfast), headers=headers).json()
    assert client.put(_url(value, breakfast), headers=headers, json=_payload(slot, notes="分頁一")).status_code == 200
    conflict = client.put(_url(value, breakfast), headers=headers, json=_payload(slot, notes="分頁二"))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "MENU_SLOT_VERSION_CONFLICT"
    assert conflict.json()["detail"]["current_fingerprint"] != slot["slot_fingerprint"]
    current = client.get(_url(value, breakfast), headers=headers).json()
    assert current["notes"] == "分頁一"
    payload = _payload(current)
    payload.pop("expected_slot_fingerprint")
    assert client.put(_url(value, breakfast), headers=headers, json=payload).status_code == 422


def test_different_meals_and_dates_have_independent_versions(client, db_session):
    headers, value, breakfast, lunch, _ = _setup(client, db_session)
    targets = [(breakfast, "2026-09-01"), (lunch, "2026-09-01"), (breakfast, "2026-09-02")]
    loaded = [(meal, day, client.get(_url(value, meal, day), headers=headers).json()) for meal, day in targets]
    for index, (meal, day, slot) in enumerate(loaded):
        response = client.put(_url(value, meal, day), headers=headers, json=_payload(slot, notes=f"分頁 {index}"))
        assert response.status_code == 200, response.text
    for index, (meal, day, _) in enumerate(loaded):
        assert client.get(_url(value, meal, day), headers=headers).json()["notes"] == f"分頁 {index}"


def test_empty_slot_version_supports_create_and_clear_without_touching_other_slots(client, db_session):
    headers, value, breakfast, _, dishes = _setup(client, db_session)
    url = _url(value, breakfast, "2026-09-03")
    empty = client.get(url, headers=headers).json()
    assert empty["menu_day_id"] is None and empty["dishes"] == []
    payload = _payload(empty, dishes=[{"dish_id": dishes[0]["id"], "diner_count": 12}])
    response = client.put(url, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    stale = client.put(url, headers=headers, json=payload)
    assert stale.status_code == 409
    slot = client.get(url, headers=headers).json()
    assert slot["menu_day_id"] is not None
    assert client.put(url, headers=headers, json=_payload(slot, dishes=[], notes=None)).status_code == 200
    assert client.get(url, headers=headers).json()["dishes"] == []
    assert len(_editor(client, headers, value)["slots"]) == 5


@pytest.mark.parametrize("legacy_first", [False, True])
def test_new_and_legacy_editor_cannot_overwrite_each_others_saved_changes(client, db_session, legacy_first):
    headers, value, breakfast, _, _ = _setup(client, db_session)
    aggregate = _editor(client, headers, value)
    slot = client.get(_url(value, breakfast), headers=headers).json()
    editor_url = f"/api/v1/menus/{value['id']}/editor"
    editor_payload = {"slots": aggregate["slots"], "expected_editor_fingerprint": aggregate["editor_fingerprint"]}
    next(item for item in editor_payload["slots"] if item["menu_day_id"] == slot["menu_day_id"])["notes"] = "整份編輯器"
    if legacy_first:
        first = client.put(editor_url, headers=headers, json=editor_payload)
        second = client.put(_url(value, breakfast), headers=headers, json=_payload(slot, notes="餐次編輯器"))
    else:
        first = client.put(_url(value, breakfast), headers=headers, json=_payload(slot, notes="餐次編輯器"))
        second = client.put(editor_url, headers=headers, json=editor_payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] in {"MENU_SLOT_VERSION_CONFLICT", "MENU_VERSION_CONFLICT"}


def test_legacy_editor_requires_version_and_rejects_stale_whole_menu(client, db_session):
    headers, value, _, _, _ = _setup(client, db_session)
    editor_url = f"/api/v1/menus/{value['id']}/editor"
    original = _editor(client, headers, value)
    missing = client.put(editor_url, headers=headers, json={"slots": []})
    assert missing.status_code == 409 and missing.json()["detail"]["code"] == "MENU_VERSION_REQUIRED"
    assert _editor(client, headers, value) == original
    payload = {"slots": original["slots"], "expected_editor_fingerprint": original["editor_fingerprint"]}
    payload["slots"][1]["notes"] = "另一分頁"
    assert client.put(editor_url, headers=headers, json=payload).status_code == 200
    stale = client.put(editor_url, headers=headers, json=payload)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "MENU_VERSION_CONFLICT"


@pytest.mark.parametrize("mode", ["same", "different", "empty", "legacy", "mixed"])
def test_real_concurrent_requests_share_root_lock_and_enforce_versions(client, db_session, monkeypatch, mode):
    headers, value, breakfast, lunch, dishes = _setup(client, db_session)
    urls = [_url(value, breakfast), _url(value, lunch if mode == "different" else breakfast)]
    if mode == "empty":
        urls = [_url(value, breakfast, "2026-09-03")] * 2
    payloads = [_payload(client.get(url, headers=headers).json(), notes=f"concurrent-{index}")
                for index, url in enumerate(urls)]
    if mode == "empty":
        for payload in payloads:
            payload["dishes"] = [{"dish_id": dishes[0]["id"], "diner_count": 33}]
    if mode in {"legacy", "mixed"}:
        aggregate = _editor(client, headers, value)
        for index in ([0, 1] if mode == "legacy" else [1]):
            urls[index] = f"/api/v1/menus/{value['id']}/editor"
            payloads[index] = {"slots": copy.deepcopy(aggregate["slots"]),
                               "expected_editor_fingerprint": aggregate["editor_fingerprint"]}
            next(item for item in payloads[index]["slots"] if item["menu_date"] == "2026-09-01"
                 and item["menu_meal_type_id"] == breakfast["id"])["notes"] = f"whole-menu-{index}"
    # Both HTTP request transactions arrive at SELECT FOR UPDATE together.
    # One must wait and then read the winner's committed state, including empty slots.
    barrier = Barrier(2, timeout=10)
    original_lock = MenuRepository.menu_model

    def simultaneous_lock(repository, menu_id, for_update=False, for_share=False):
        if for_update:
            barrier.wait()
        return original_lock(repository, menu_id, for_update=for_update, for_share=for_share)

    monkeypatch.setattr(MenuRepository, "menu_model", simultaneous_lock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.put, url, headers=headers, json=payload)
                   for url, payload in zip(urls, payloads)]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == ([200, 200] if mode == "different" else [200, 409]), [r.text for r in responses]
    aggregate = _editor(client, headers, value)
    assert len({dish["id"] for slot in aggregate["slots"] for dish in slot["dishes"]}) == sum(
        len(slot["dishes"]) for slot in aggregate["slots"])
    if mode == "different":
        assert {client.get(url, headers=headers).json()["notes"] for url in urls} == {"concurrent-0", "concurrent-1"}
    else:
        winner = responses.index(next(response for response in responses if response.status_code == 200))
        current = client.get(_url(value, breakfast, "2026-09-03" if mode == "empty" else "2026-09-01"), headers=headers).json()
        assert current["notes"] == (
            f"whole-menu-{winner}" if mode == "legacy" or (mode == "mixed" and winner == 1) else f"concurrent-{winner}")


def test_audit_failure_rolls_back_deletes_inserts_and_all_fields(client, db_session, monkeypatch):
    headers, value, breakfast, _, dishes = _setup(client, db_session)
    before = _editor(client, headers, value)
    slot = client.get(_url(value, breakfast), headers=headers).json()
    audit_count = db_session.scalar(select(func.count()).select_from(AuditLog))

    def fail_audit(*args, **kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(AuditLogService, "record", fail_audit)
    payload = _payload(slot, notes="rollback", dishes=[{"dish_id": dishes[3]["id"], "diner_count": 99}])
    response = client.put(_url(value, breakfast), headers=headers, json=payload)
    assert response.status_code == 400
    assert _editor(client, headers, value) == before
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == audit_count


@pytest.mark.parametrize("invalid", ["date", "meal", "menu", "day", "dish_identity", "unknown_dish", "duplicate", "count", "version"])
def test_invalid_input_or_identity_is_rejected_atomically(client, db_session, invalid):
    headers, value, breakfast, lunch, dishes = _setup(client, db_session)
    before = _editor(client, headers, value)
    url = _url(value, breakfast)
    slot = client.get(url, headers=headers).json()
    payload = _payload(slot)
    expected = 422
    if invalid == "date": url = _url(value, breakfast, "2026-09-10")
    elif invalid == "meal": url = _url(value, {"id": str(uuid.uuid4())}); expected = 404
    elif invalid == "menu": url = url.replace(value["id"], str(uuid.uuid4())); expected = 404
    elif invalid == "day": payload["menu_day_id"] = str(uuid.uuid4())
    elif invalid == "dish_identity": payload["dishes"][0]["dish_id"] = dishes[2]["id"]
    elif invalid == "unknown_dish": payload["dishes"] = [{"dish_id": str(uuid.uuid4())}]
    elif invalid == "duplicate": payload["dishes"] *= 2; expected = 409
    elif invalid == "count": payload["dishes"][0]["diner_count"] = -1
    elif invalid == "version": payload["expected_slot_fingerprint"] = "not-a-fingerprint"
    response = client.put(url, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    assert _editor(client, headers, value) == before


def test_column_from_another_meal_is_rejected(client, db_session):
    headers, value, breakfast, lunch, _ = _setup(client, db_session)
    column = client.post(f"/api/v1/menus/{value['id']}/meal-types/{lunch['id']}/columns",
                         headers=headers, json={"name": "午餐欄位"}).json()
    slot = client.get(_url(value, breakfast), headers=headers).json()
    payload = _payload(slot)
    payload["dishes"][0]["menu_meal_type_column_id"] = column["id"]
    assert client.put(_url(value, breakfast), headers=headers, json=payload).status_code == 422
    assert client.get(_url(value, breakfast), headers=headers).json() == slot


def test_auth_and_inactive_assignment_rules_match_existing_editor(client, db_session):
    headers, value, breakfast, _, dishes = _setup(client, db_session)
    url = _url(value, breakfast)
    slot = client.get(url, headers=headers).json()
    assert client.get(url).status_code == 401
    assert client.put(url, json=_payload(slot)).status_code == 401
    assert client.post(f"/api/v1/dishes/{dishes[2]['id']}/deactivate", headers=headers).status_code == 200
    payload = _payload(slot)
    payload["dishes"].append({"dish_id": dishes[2]["id"]})
    assert client.put(url, headers=headers, json=payload).status_code == 422
    assert client.get(url, headers=headers).json() == slot
    assert client.post(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/deactivate", headers=headers).status_code == 200
    inactive = client.get(url, headers=headers).json()
    assert inactive["slot_fingerprint"] != slot["slot_fingerprint"]
    payload = _payload(inactive, notes="保留歷史餐次")
    payload["dishes"][0]["diner_count"] = 88
    assert client.put(url, headers=headers, json=payload).status_code == 200
    current = client.get(url, headers=headers).json()
    payload = _payload(current)
    payload["dishes"].append({"dish_id": dishes[3]["id"]})
    assert client.put(url, headers=headers, json=payload).status_code == 422
    assert client.get(url, headers=headers).json() == current


def test_long_lived_session_refreshes_locked_models_after_another_writer(client, db_session):
    headers, value, breakfast, _, _ = _setup(client, db_session)
    with SessionLocal() as session:
        service = MenuService(session)
        aggregate = service.aggregate(uuid.UUID(value["id"]))
        session.rollback()  # Release read lock, retain the loaded identity map.
        slot = client.get(_url(value, breakfast), headers=headers).json()
        assert client.put(_url(value, breakfast), headers=headers, json=_payload(slot, notes="other writer")).status_code == 200
        current = service.meal_slot(uuid.UUID(value["id"]), uuid.UUID(breakfast["id"]), date(2026, 9, 1))
        assert current["notes"] == "other writer"
        assert current["slot_fingerprint"] != slot["slot_fingerprint"]
        assert aggregate["editor_fingerprint"] != service.aggregate(uuid.UUID(value["id"]))["editor_fingerprint"]
