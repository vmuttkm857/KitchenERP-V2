"""H07 exercises the real calculator, snapshot writer and route error mapping.

Only repository/session I/O and the post-commit detail read are replaced.
"""

from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.routes import snapshots as routes
from app.domains.snapshots import service as snapshots
from app.domains.snapshots.fingerprint import content_fingerprint
from app.domains.snapshots.models import RequirementSnapshot, RequirementSnapshotItem
from app.domains.snapshots.schemas import SnapshotCreate
from tests.unit.requirements.test_confirmed_adjustment_coverage import SavedSources


@pytest.fixture
def flow(monkeypatch):
    world = SavedSources(monkeypatch)
    world.live = [world.row()]
    added, audits, operations = [], [], []
    session = SimpleNamespace(
        flush=lambda: operations.append("flush"),
        commit=lambda: operations.append("commit"),
        rollback=lambda: operations.append("rollback"),
    )

    def add(value):
        value.id = value.id or uuid4()
        added.append(value)

    repository = SimpleNamespace(
        lock_creation_key=lambda key: operations.append("creation_lock"),
        by_content=lambda *args: None,
        next_revision=lambda key: 1,
        add=add,
    )
    monkeypatch.setattr(snapshots, "SnapshotRepository", lambda _: repository)
    monkeypatch.setattr(snapshots, "AuditLogService", lambda _: SimpleNamespace(record=lambda **values: audits.append(values)))
    monkeypatch.setattr(snapshots.SnapshotService, "detail", lambda self, snapshot_id: {"id": snapshot_id})
    monkeypatch.setattr(routes, "SnapshotDetail", SimpleNamespace(model_validate=lambda value: value))
    actor = SimpleNamespace(id=uuid4())

    def save(viewed, *, criteria=None, fingerprint=None):
        # Pre-fix reproduction: the legacy endpoint ignores this extra field.
        # After the fix the real calculation response supplies the required token.
        expected = fingerprint if fingerprint is not None else viewed.get("result_fingerprint", content_fingerprint(viewed))
        data = SnapshotCreate.model_validate({
            "criteria": (criteria or viewed["criteria"]).model_dump(mode="json", exclude_none=True),
            "expected_result_fingerprint": expected,
        })
        return routes.create(data, actor, session)

    return SimpleNamespace(world=world, added=added, audits=audits, operations=operations,
                           session=session, repository=repository, save=save, actor=actor)


@pytest.mark.parametrize("change", ["recipe", "menu", "manual", "price", "empty", "unit"])
def test_changed_source_is_rejected_before_any_snapshot_write(flow, change):
    world = flow.world
    sheet = world.capture(world.live, status="draft") if change == "manual" else None
    viewed = world.calculate([sheet] if sheet else [])
    if change == "recipe":
        world.live[0]["recipe_quantity"] = Decimal("200")
    elif change == "menu":
        world.live = [world.row(ingredient_id=uuid4(), ingredient_code="NEW", dish_name="新菜")]
    elif change == "manual":
        line = world.saved_lines(sheet)[0]
        line.adjusted_quantity, line.adjusted_unit = Decimal("7.25"), "kg"
    elif change == "price":
        world.live[0]["current_price"] = Decimal("99.5")
    elif change == "empty":
        world.live.clear()
    else:
        world.live[0]["recipe_unit"] = "片"
    with pytest.raises(HTTPException) as caught:
        flow.save(viewed)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "SNAPSHOT_RESULT_CHANGED"
    assert flow.added == [] and flow.audits == []
    assert "commit" not in flow.operations and "rollback" in flow.operations


def test_unchanged_result_saves_server_values_and_preserves_existing_history(flow):
    world = flow.world
    sheet = world.capture(world.live)
    history = deepcopy(world.snapshots[sheet.baseline_snapshot_id].__dict__)
    viewed = world.calculate([sheet])
    response = flow.save(viewed)
    header = next(value for value in flow.added if isinstance(value, RequirementSnapshot))
    item = next(value for value in flow.added if isinstance(value, RequirementSnapshotItem))
    row = viewed["rows"][0]
    assert response["id"] == header.id and header.snapshot_kind == "standard"
    assert item.requirement_quantity == row["requirement_quantity"] == Decimal("2.5")
    assert item.source_summary == snapshots.normalize(row["schedules"])
    assert header.content_fingerprint == content_fingerprint(viewed)
    assert flow.operations.count("commit") == 1 and len(flow.audits) == 1
    assert world.snapshots[sheet.baseline_snapshot_id].__dict__ == history


def test_verified_result_is_not_recalculated_after_source_changes_before_writing(flow):
    world = flow.world
    viewed = world.calculate()
    reads = []
    original = snapshots.RequirementService.calculate

    def calculate(self, criteria):
        reads.append(criteria)
        return original(self, criteria)

    def source_changes_while_waiting_for_creation_lock(key):
        world.live[0]["recipe_quantity"] = Decimal("999")
        flow.operations.append("creation_lock")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(snapshots.RequirementService, "calculate", calculate)
        patch.setattr(flow.repository, "lock_creation_key", source_changes_while_waiting_for_creation_lock)
        flow.save(viewed)
    item = next(value for value in flow.added if isinstance(value, RequirementSnapshotItem))
    assert len(reads) == 1
    assert item.requirement_quantity == viewed["rows"][0]["requirement_quantity"]
    assert item.source_summary == snapshots.normalize(viewed["rows"][0]["schedules"])
    assert world.live[0]["recipe_quantity"] == Decimal("999")


def test_row_and_schedule_order_do_not_cause_false_conflicts(flow):
    world = flow.world
    world.live += [world.row(dish_name="另一道菜"), world.row(ingredient_id=uuid4(), ingredient_code="OTHER")]
    viewed = world.calculate()
    world.live.reverse()
    flow.save(viewed)
    assert "commit" in flow.operations


@pytest.mark.parametrize("field", [
    "row_key", "ingredient_id", "ingredient_code", "ingredient_name", "supplier_id", "supplier_code", "supplier_name", "requirement_quantity",
    "requirement_unit", "suggested_purchase_quantity", "suggested_purchase_unit", "configured_purchase_unit",
    "package_size", "minimum_order_quantity", "current_price", "estimated_cost", "needs_review",
    "total_diner_count", "source_count", "schedules",
])
def test_fingerprint_covers_snapshot_item_content(flow, field):
    from app.domains.snapshots.fingerprint import result_fingerprint
    original = flow.world.calculate()
    changed = deepcopy(original)
    row = changed["rows"][0]
    value = row[field]
    if field == "schedules": row[field][0]["dish_id"] = str(uuid4())
    elif isinstance(value, Decimal): row[field] += Decimal("0.1")
    elif isinstance(value, bool): row[field] = not value
    elif isinstance(value, int): row[field] += 1
    elif field.endswith("_id"): row[field] = uuid4()
    else: row[field] = str(value) + "changed"
    assert result_fingerprint(original) != result_fingerprint(changed)


@pytest.mark.parametrize("field", ["source_menus", "anomalies", "anomaly_summary", "known_estimated_cost", "total_estimated_cost"])
def test_fingerprint_covers_snapshot_header_content(flow, field):
    from app.domains.snapshots.fingerprint import result_fingerprint
    original = flow.world.calculate()
    changed = deepcopy(original)
    if field == "source_menus": changed[field][0]["menu_name"] = "新菜單名稱"
    elif field == "anomalies": changed[field].append({"code": "WARNING", "context": {}})
    elif field == "anomaly_summary": changed[field]["warnings"] += 1
    else: changed[field] += Decimal("0.1")
    assert result_fingerprint(original) != result_fingerprint(changed)


def test_fingerprint_distinguishes_criteria_modes_dates_and_menu_ids(flow):
    from app.domains.snapshots.fingerprint import result_fingerprint
    original = flow.world.calculate()
    for change in ({"menu_ids": [uuid4()]}, {"selected_dates": [date(2026, 11, 3)]},
                   {"ordering_adjustment_sheet_ids": [uuid4()]}):
        changed = deepcopy(original)
        changed["criteria"] = changed["criteria"].model_copy(update=change)
        assert result_fingerprint(original) != result_fingerprint(changed)


def test_canonical_fingerprint_ignores_derived_views_order_and_decimal_scale(flow):
    from app.domains.snapshots.fingerprint import result_fingerprint
    original = flow.world.calculate()
    changed = deepcopy(original)
    changed["rows"][0]["requirement_quantity"] = Decimal("2.500000")
    changed["daily_rows"] = []
    changed["supplier_groups"] = []
    changed["rows"][0]["base_unit"] = "display-only"
    changed["result_fingerprint"] = "not-part-of-the-content"
    assert result_fingerprint(original) == result_fingerprint(changed)
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        assert result_fingerprint(original) == result_fingerprint(changed)


def test_fingerprint_never_rounds_decimal_digits_during_hashing(flow):
    from app.domains.snapshots.fingerprint import result_fingerprint
    original = flow.world.calculate()
    original["rows"][0]["requirement_quantity"] = Decimal("0.123456789123456789123456789123")
    changed = deepcopy(original)
    changed["rows"][0]["requirement_quantity"] = Decimal("0.123456789123456789123456789124")
    assert result_fingerprint(original) != result_fingerprint(changed)


def test_wire_response_exposes_an_opaque_fingerprint_without_changing_decimals(flow):
    from app.domains.requirements.schemas import RequirementResult
    result = flow.world.calculate()
    wire = RequirementResult.model_validate(result).model_dump(mode="json")
    assert wire["result_fingerprint"] == result["result_fingerprint"]
    assert Decimal(wire["rows"][0]["requirement_quantity"]) == Decimal("2.5")
    assert wire["daily_rows"][0]["requirement_date"] == "2026-11-02"


def test_old_service_call_without_a_fingerprint_fails_closed(flow):
    from app.domains.snapshots.exceptions import SnapshotResultFingerprintError
    with pytest.raises(SnapshotResultFingerprintError):
        snapshots.SnapshotService(flow.session).create(flow.world.calculate()["criteria"], flow.actor.id)
    assert flow.added == [] and "commit" not in flow.operations


@pytest.mark.parametrize("different_criteria", ["dates", "menus", "actual"])
def test_a_valid_fingerprint_from_other_conditions_cannot_be_reused(flow, different_criteria):
    world = flow.world
    viewed = world.calculate()
    criteria = viewed["criteria"]
    if different_criteria == "dates":
        criteria = criteria.model_copy(update={"selected_dates": [date(2026, 11, 2)]})
    elif different_criteria == "actual":
        sheet = world.capture(world.live)
        criteria = criteria.model_copy(update={"ordering_adjustment_sheet_ids": [sheet.id]})
    else:
        other = uuid4()
        world.add_menu(other)
        world.live.append(world.row(menu_id=other))
        criteria = criteria.model_copy(update={"menu_ids": [other]})
    with pytest.raises(HTTPException) as caught:
        flow.save(viewed, criteria=criteria)
    assert caught.value.status_code == 409 and flow.added == []


def test_item_write_failure_still_rolls_back_instead_of_committing(flow):
    original_add = flow.repository.add

    def add(value):
        if isinstance(value, RequirementSnapshotItem):raise RuntimeError("injected failure")
        original_add(value)

    flow.repository.add = add
    with pytest.raises(HTTPException):
        flow.save(flow.world.calculate())
    assert "rollback" in flow.operations and "commit" not in flow.operations


@pytest.mark.parametrize("value", [None, "", "bad", "a" * 63, "z" * 64])
def test_missing_or_invalid_fingerprint_is_not_accepted(flow, value):
    payload = {"criteria": flow.world.calculate()["criteria"].model_dump(mode="json")}
    if value is not None: payload["expected_result_fingerprint"] = value
    with pytest.raises(ValidationError):
        SnapshotCreate.model_validate(payload)
    assert flow.added == []
