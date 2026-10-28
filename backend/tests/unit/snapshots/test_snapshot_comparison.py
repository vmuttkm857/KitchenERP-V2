from copy import deepcopy
from decimal import Decimal
from typing import get_args

import pytest

from app.domains.snapshots.schemas import SnapshotHeaderPublic, SnapshotItemPublic
from tests.snapshot_comparison import HEADER_DECIMAL_FIELDS, ITEM_DECIMAL_FIELDS, assert_snapshot_unchanged


@pytest.fixture
def snapshot():
    return {
        "id": "snapshot-1", "revision": 1, "fingerprint": "001.00", "content_fingerprint": "001.00",
        "known_estimated_cost": "1680.5000000000", "total_estimated_cost": "1680.5000000000",
        "created_at": "2026-09-01T00:00:00Z", "created_by": "user-1",
        "criteria": {"selected_dates": ["2026-09-01"], "menu_ids": ["menu-1"]},
        "source_menus": [{"menu_id": "menu-1", "menu_name": "001.00", "start_date": "2026-09-01"}],
        "items": [{
            "id": "item-1", "row_key": "ingredient-1:kg", "ingredient_id": "ingredient-1",
            "ingredient_code_snapshot": "001.00", "ingredient_name_snapshot": "食材",
            "supplier_id": "supplier-1", "supplier_code_snapshot": "001.00", "supplier_name_snapshot": "供應商",
            "requirement_quantity": "3.150000", "requirement_unit": "kg",
            "suggested_purchase_quantity": "3.150000", "adjusted_quantity": "3.150000",
            "package_size_snapshot": "1.000000", "minimum_order_quantity_snapshot": "0.000000",
            "unit_price_snapshot": "200.000000", "estimated_cost_snapshot": "630.000000",
            "adjusted_estimated_cost": "630.000000000000", "needs_review": False, "source_count": 1,
            "source_summary": [{"menu_id": "menu-1", "dish_id": "dish-1", "requirement_date": "2026-09-01",
                                "quantity": "3.15", "unit": "kg"}],
        }],
    }


def test_tail_zero_difference_does_not_mean_snapshot_changed(snapshot):
    actual = deepcopy(snapshot)
    actual.update(known_estimated_cost="1680.500000", total_estimated_cost="1680.500000")
    assert actual != snapshot  # Reproduces the original strict JSON assertion.
    assert_snapshot_unchanged(actual, snapshot)


@pytest.mark.parametrize("field", sorted(HEADER_DECIMAL_FIELDS))
def test_real_money_difference_is_not_ignored(snapshot, field):
    actual = deepcopy(snapshot)
    actual[field] = "1680.500001"
    with pytest.raises(AssertionError):
        assert_snapshot_unchanged(actual, snapshot)


@pytest.mark.parametrize("field", sorted(ITEM_DECIMAL_FIELDS))
def test_only_declared_item_decimals_accept_equal_scale_changes(snapshot, field):
    actual = deepcopy(snapshot)
    actual["items"][0][field] += "00"
    assert_snapshot_unchanged(actual, snapshot)
    actual["items"][0][field] = str(Decimal(snapshot["items"][0][field]) + Decimal("0.000001"))
    with pytest.raises(AssertionError):
        assert_snapshot_unchanged(actual, snapshot)


@pytest.mark.parametrize("path,replacement", [
    (("items", 0, "ingredient_id"), "ingredient-2"),
    (("items", 0, "id"), "item-2"),
    (("items", 0, "source_summary", 0, "dish_id"), "dish-2"),
    (("items", 0, "source_summary", 0, "menu_id"), "menu-2"),
    (("items", 0, "source_summary", 0, "requirement_date"), "2026-09-02"),
    (("items", 0, "source_summary", 0, "quantity"), "3.1500"),
    (("items", 0, "supplier_id"), "supplier-2"),
    (("items", 0, "requirement_unit"), "斤"),
    (("items", 0, "ingredient_code_snapshot"), "1.0"),
    (("items", 0, "supplier_code_snapshot"), "1.0"),
    (("source_menus", 0, "menu_name"), "1.0"),
    (("criteria", "selected_dates", 0), "2026-09-02"),
    (("fingerprint",), "1.0"),
    (("content_fingerprint",), "1.0"),
    (("created_at",), "2026-09-02T00:00:00Z"),
    (("items", 0, "needs_review"), 0),
])
def test_nondecimal_content_and_source_json_remain_strict(snapshot, path, replacement):
    actual = deepcopy(snapshot)
    node = actual
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = replacement
    with pytest.raises(AssertionError):
        assert_snapshot_unchanged(actual, snapshot)


@pytest.mark.parametrize("change", ["missing_field", "extra_field", "missing_item", "extra_item", "item_order"])
def test_snapshot_structure_and_every_item_remain_protected(snapshot, change):
    snapshot["items"].append({**deepcopy(snapshot["items"][0]), "id": "item-2"})
    actual = deepcopy(snapshot)
    if change == "missing_field":
        del actual["items"][0]["adjusted_quantity"]
    elif change == "extra_field":
        actual["items"][0]["unexpected"] = "value"
    elif change == "missing_item":
        actual["items"].pop()
    elif change == "extra_item":
        actual["items"].append(deepcopy(actual["items"][0]))
    else:
        actual["items"].reverse()
    with pytest.raises(AssertionError):
        assert_snapshot_unchanged(actual, snapshot)


@pytest.mark.parametrize("value", [None, "bad", "NaN", "Infinity", 1680.5])
def test_invalid_or_type_changed_decimal_does_not_pass(snapshot, value):
    actual = deepcopy(snapshot)
    actual["known_estimated_cost"] = value
    with pytest.raises(AssertionError):
        assert_snapshot_unchanged(actual, snapshot)


def test_nullable_decimal_remains_nullable_without_becoming_zero(snapshot):
    snapshot["total_estimated_cost"] = None
    actual = deepcopy(snapshot)
    assert_snapshot_unchanged(actual, snapshot)
    actual["total_estimated_cost"] = "0"
    with pytest.raises(AssertionError):
        assert_snapshot_unchanged(actual, snapshot)


def test_allowlists_match_actual_api_decimal_fields():
    def decimal_fields(model):
        return {name for name, field in model.model_fields.items()
                if field.annotation is Decimal or Decimal in get_args(field.annotation)}
    assert HEADER_DECIMAL_FIELDS == decimal_fields(SnapshotHeaderPublic)
    assert ITEM_DECIMAL_FIELDS == decimal_fields(SnapshotItemPublic)


def test_existing_api_serializer_preserves_decimal_scale_without_fixed_width():
    field = dict(id="00000000-0000-0000-0000-000000000001", fingerprint="f", criteria_fingerprint="c",
                 content_fingerprint="x", revision=1, criteria={}, source_menus=[], anomaly_snapshot=[], anomaly_summary={},
                 known_estimated_cost=Decimal("1680.5000000000"), total_estimated_cost=Decimal("1680.5000000000"),
                 created_at="2026-09-01T00:00:00Z", created_by="00000000-0000-0000-0000-000000000002")
    post = SnapshotHeaderPublic.model_validate(field).model_dump(mode="json")
    field.update(known_estimated_cost=Decimal("1680.500000"), total_estimated_cost=Decimal("1680.500000"))
    get = SnapshotHeaderPublic.model_validate(field).model_dump(mode="json")
    assert post["known_estimated_cost"] == "1680.5000000000"
    assert get["known_estimated_cost"] == "1680.500000"
    assert_snapshot_unchanged(get, post)
