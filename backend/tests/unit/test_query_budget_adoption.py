"""Protect every original API query limit; offline behavior tests never open a DB."""

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, text

from app.domains.order_adjustments.models import OrderingAdjustmentSheet
from app.domains.order_adjustments.service import OrderingAdjustmentService, _source_fingerprint
from app.domains.requirements.schemas import RequirementCriteria
from app.domains.snapshots.models import RequirementSnapshot
from app.domains.users.models import User
from tests.query_budget import SelectQueryBudget
from tests.unit.snapshots.test_query_budget import guard_queries, record


# Complete baseline: 31 API tests, 32 measurement windows; includes two already fixed snapshots.
API_QUERY_BUDGETS = (
    ('api/auth/test_users_audit.py', 'test_audit_before_after_sanitization_snapshot_filters_and_query_budget', (3,)),
    ('api/dishes_recipes/test_dishes_recipes_api.py', 'test_recipe_aggregate_query_count_is_constant', (3,)),
    ('api/dishes_recipes/test_dishes_recipes_api.py', 'test_dish_list_includes_recipe_ingredient_count_with_fixed_query_budget', (3,)),
    ('api/exports/test_exports_api.py', 'test_kitchen_a4_export_query_count_does_not_grow_per_row', (4,)),
    ('api/exports/test_exports_api.py', 'test_kitchen_export_query_count_does_not_grow_per_row', (4,)),
    ('api/exports/test_exports_api.py', 'test_menu_export_query_budget_is_constant', (5,)),
    ('api/exports/test_exports_api.py', 'test_menu_nutrition_exports_are_opt_in_complete_and_deduplicated', (9,)),
    ('api/exports/test_exports_api.py', 'test_kitchen_simple_excel_pdf_known_answer_anomaly_and_query_budget', (5,)),
    ('api/kitchen_operations/test_kitchen_operations_api.py', 'test_auth_query_budget_read_only_and_no_snapshot_purchase_dependency', (4,)),
    ('api/master_data/test_master_data_api.py', 'test_ingredient_list_has_constant_query_count', (3,)),
    ('api/master_data/test_master_data_api.py', 'test_ingredient_list_supplier_filter_combinations_and_pagination', (3,)),
    ('api/master_data/test_supplier_enhancements.py', 'test_supplier_fields_ordering_filters_pagination_and_query_budget', (3,)),
    ('api/menus/test_menus_api.py', 'test_aggregate_query_count_constant_and_fk', (5,)),
    ('api/nutrition/test_dish_nutrition_api.py', 'test_bulk_nutrition_has_constant_query_count_and_reuses_duplicate_dish', (5,)),
    ('api/nutrition/test_nutrition_api.py', 'test_food_lists_and_ingredient_status_use_bounded_queries', (7,)),
    ('api/order_adjustments/test_order_adjustments_api.py', 'test_reuse_preview_and_apply_are_authoritative_versioned_and_audited', (10,)),
    ('api/order_adjustments/test_order_adjustments_api.py', 'test_list_is_authenticated_paginated_and_constant_query_count', (4,)),
    ('api/postpartum/test_case_restriction_groups_api.py', 'test_assignment_audit_and_case_list_fixed_query_budget', (4,)),
    ('api/postpartum/test_catering_overview_api.py', 'test_catering_overview_has_fixed_read_only_query_budget', (4,)),
    ('api/postpartum/test_change_sheet_api.py', 'test_change_sheet_uses_fixed_read_queries_and_never_writes', (15,)),
    ('api/postpartum/test_change_sheet_api.py', 'test_daily_change_sheet_uses_one_fixed_read_preload_and_never_writes', (15,)),
    ('api/postpartum/test_menu_conflicts_api.py', 'test_conflicts_exact_matching_eligibility_partial_coverage_and_read_only', (9,)),
    ('api/postpartum/test_menu_conflicts_api.py', 'test_complete_no_conflict_and_query_count_is_fixed', (9,)),
    ('api/postpartum/test_menu_conflicts_api.py', 'test_daily_conflicts_return_six_canonical_meals_and_case_details', (9,)),
    ('api/postpartum/test_menu_conflicts_api.py', 'test_weekly_conflicts_are_monday_to_sunday_with_7_by_6_fixed_query_budget', (9,)),
    ('api/postpartum/test_replacements_api.py', 'test_candidate_search_create_cancel_and_audit', (12, 14)),
    ('api/purchases/test_purchases_api.py', 'test_list_pagination_filters_and_detail_query_budget', (5,)),
    ('api/purchases/test_purchases_api.py', 'test_creation_query_count_does_not_scale_per_item', (8,)),
    ('api/requirements/test_requirements_api.py', 'test_requirement_query_count_is_constant_and_read_only', (3,)),
    ('api/snapshots/test_snapshots_api.py', 'test_snapshot_list_date_filters_end_inclusive_pagination_order_and_query_budget', (3,)),
    ('api/snapshots/test_snapshots_api.py', 'test_detail_query_count_is_constant', (4,)),
)


@pytest.mark.parametrize("relative,name,limits", API_QUERY_BUDGETS, ids=[item[1] for item in API_QUERY_BUDGETS])
def test_all_api_budgets_use_shared_counter_and_keep_original_limits(relative, name, limits):
    source = (Path(__file__).resolve().parents[1] / relative).read_text(encoding="utf-8")
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    constructors = sorted([
        n for n in ast.walk(function)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "SelectQueryBudget"
    ], key=lambda n: n.lineno)
    assert tuple(next(k.value.value for k in n.keywords if k.arg == "maximum") for n in constructors) == limits
    listeners = [n for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "listen"]
    assert len(listeners) == len(limits)
    if relative != "api/snapshots/test_snapshots_api.py":
        comparisons = sorted([
            n for n in ast.walk(function)
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Attribute)
            and isinstance(n.left.value, ast.Name) and n.left.value.id == "budget"
            and n.left.attr == "business_selects"
        ], key=lambda n: n.lineno)
        assert tuple(n.comparators[0].value for n in comparisons) == limits
        assert all(len(n.ops) == 1 and isinstance(n.ops[0], ast.LtE) for n in comparisons)
        callbacks = {n.args[2].id for n in listeners}
        for callback in (n for n in function.body if isinstance(n, ast.FunctionDef) and n.name in callbacks):
            assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and isinstance(n.func.value, ast.Name) and n.func.value.id == "budget"
                       and n.func.attr == "record" for n in ast.walk(callback))


def test_inventory_covers_all_physical_sql_counters_in_api_integration_and_regression():
    root = Path(__file__).resolve().parents[1]
    found = set()
    for directory in ("api", "integration", "regression"):
        for path in (root / directory).rglob("*.py"):
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                    continue
                if any(isinstance(n, ast.Constant) and n.value in {"before_cursor_execute", "after_cursor_execute"}
                       for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)):
                    found.add((path.relative_to(root).as_posix(), node.name))
    assert found == {(path, name) for path, name, _ in API_QUERY_BUDGETS}


@pytest.mark.parametrize("maximum", sorted({n for _, _, limits in API_QUERY_BUDGETS for n in limits}))
def test_each_existing_threshold_counts_auth_and_rejects_one_more_business_select(maximum):
    budget = SelectQueryBudget(maximum=maximum)
    guard_queries(budget)
    record(budget, select(User).where(User.id == UUID(int=1)))
    assert budget.business_selects == 1  # Authentication remains inside every budget.
    for _ in range(maximum - 1):
        record(budget, text("SELECT id FROM ordering_adjustment_sheets"))
    budget.assert_within_budget()
    assert sum(budget.safety_selects.values()) == 3
    record(budget, text("SELECT id FROM ingredients"))
    assert budget.business_selects == maximum + 1
    with pytest.raises(AssertionError, match=f"{maximum + 1} > {maximum}"):
        budget.assert_within_budget()


def test_multiple_request_checkouts_exclude_only_their_actual_guard_sql():
    budget = SelectQueryBudget(maximum=7)
    for reads in (3, 4):
        guard_queries(budget)
        record(budget, select(User).where(User.id == UUID(int=1)))
        for _ in range(reads - 1):
            record(budget, text("SELECT id FROM ingredients"))
    assert budget.business_selects == 7  # Both authentication reads still count.
    assert dict(budget.safety_selects) == {
        "database_identity": 2, "competing_sessions": 2, "application_name": 2,
    }
    budget.assert_within_budget()
    record(budget, text("SELECT id FROM suppliers"))
    with pytest.raises(AssertionError, match="8 > 7"):
        budget.assert_within_budget()


def ordering_list_queries(budget, sheet_count):
    record(budget, select(User).where(User.id == UUID(int=1)))
    criteria = RequirementCriteria(menu_ids=[UUID(int=2)])
    rows = [(
        OrderingAdjustmentSheet(id=UUID(int=3 + index), status="draft",
                                source_fingerprint=_source_fingerprint(criteria, [])),
        RequirementSnapshot(criteria=criteria.model_dump(mode="json", exclude_none=True), source_menus=[]),
        "offline-user",
    ) for index in range(sheet_count)]
    clauses = []

    class Session:
        def scalar(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return sheet_count

        def execute(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return SimpleNamespace(all=lambda: rows, mappings=lambda: [])

    values, total = OrderingAdjustmentService(Session()).list(1, 25)
    assert total == sheet_count and len(values) == sheet_count
    assert all(value["stale"] is False for value in values)
    return clauses


@pytest.mark.parametrize("sheet_count", [1, 5])
def test_ordering_list_is_four_queries_with_auth_and_one_batched_source_read(sheet_count):
    budget = SelectQueryBudget(maximum=4)
    guard_queries(budget)
    clauses = ordering_list_queries(budget, sheet_count)
    assert len(clauses) == 3
    assert "count(" in str(clauses[0]).lower()
    assert "ordering_adjustment_sheets" in str(clauses[1])
    assert "menu_dishes" in str(clauses[2])
    assert budget.business_selects == 4
    assert sum(budget.safety_selects.values()) == 3
    budget.assert_within_budget()


def test_fifth_ordering_list_business_query_is_not_hidden_by_guard_exclusions():
    budget = SelectQueryBudget(maximum=4)
    guard_queries(budget)
    ordering_list_queries(budget, 1)
    record(budget, text("SELECT id FROM suppliers"))
    with pytest.raises(AssertionError, match="5 > 4"):
        budget.assert_within_budget()
