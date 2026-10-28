"""Real guard/repository SQL construction, with no database or real parameters."""

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import psycopg

from app.domains.snapshots.repository import SnapshotRepository
from app.domains.snapshots.models import RequirementSnapshot
from app.domains.snapshots.service import SnapshotService
from app.domains.users.models import User
from tests.database_safety import (
    UnsafeTestDatabase, test_database_target as resolve_target, verify_connection,
)
from tests.query_budget import SelectQueryBudget


def record(budget, clause):
    compiled = clause.compile(dialect=psycopg.dialect())
    budget.record(None, None, str(compiled), None, SimpleNamespace(compiled=compiled), False)


def guard_queries(budget, *, injected_sql=None, wrong_identity=False):
    url = ("postgresql+psycopg://kitchenerp_regression_test@127.0.0.1:5432/"
           "kitchenerp_regression_test_0123456789abcdef0123456789abcdef")
    target = resolve_target("regression", {"APP_ENV": "test", "REGRESSION_TEST_DATABASE_URL": url,
                                          "DATABASE_URL": url, "TEST_DATABASE_URL": url})
    actual = dict(database_name=target.url.database, current_role=target.url.username,
                  session_role=target.url.username, server_address="127.0.0.1", server_port=5432,
                  owner_role=target.url.username, marker=target.marker, in_recovery=False,
                  is_superuser=False, can_create_db=False, can_create_role=False,
                  can_replicate=False, bypass_rls=False, role_memberships=0)
    if wrong_identity:
        actual["database_name"] = "kitchenerp_test"
    clauses = []

    class Connection:
        injected = False

        def execute(self, clause, parameters=None):
            if injected_sql is not None and not self.injected:
                self.injected = True
                record(budget, text(injected_sql))
            record(budget, clause)
            clauses.append(clause)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: actual))

        def scalar(self, clause, parameters=None):
            record(budget, clause)
            clauses.append(clause)
            return 0

        def rollback(self):
            pass

        def commit(self):
            pass

    verify_connection(Connection(), target, "offline-query-budget")
    return clauses


def list_queries(budget):
    # Include the real API's authentication read in the original three-query limit.
    record(budget, select(User).where(User.id == UUID(int=1)))
    clauses = []

    class Session:
        def scalar(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return 2

        def execute(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return SimpleNamespace(all=lambda: [])

    SnapshotRepository(Session()).list(1, 25)
    return clauses


def test_six_selects_split_into_three_safety_one_auth_and_two_list_queries():
    budget = SelectQueryBudget(maximum=3)
    guard = guard_queries(budget)
    listing = list_queries(budget)
    assert len(guard) == 3 and len(listing) == 2
    assert budget.business_selects == 3
    assert dict(budget.safety_selects) == {
        "database_identity": 1, "competing_sessions": 1, "application_name": 1,
    }
    budget.assert_within_budget()


def test_actual_repository_count_and_page_selects_are_both_counted():
    budget = SelectQueryBudget(maximum=3)
    clauses = list_queries(budget)
    assert "count(" in str(clauses[0]).lower()
    assert "requirement_snapshots" in str(clauses[1])
    assert "ORDER BY" in str(clauses[1]) and "LIMIT" in str(clauses[1])
    assert budget.business_selects == 3


def test_fourth_business_select_still_fails_original_limit():
    budget = SelectQueryBudget(maximum=3)
    guard_queries(budget)
    list_queries(budget)
    record(budget, text("SELECT ingredient_id FROM requirement_snapshot_items"))
    assert budget.business_selects == 4
    with pytest.raises(AssertionError, match="4 > 3"):
        budget.assert_within_budget()


def detail_queries(budget):
    record(budget, select(User).where(User.id == UUID(int=1)))
    header = RequirementSnapshot(id=UUID(int=2))
    clauses = []

    class Session:
        def execute(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return SimpleNamespace(first=lambda: (header, "offline-user", None, None))

        def scalars(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return []

        def scalar(self, clause):
            record(budget, clause)
            clauses.append(clause)
            return None

    SnapshotService(Session()).detail(header.id)
    return clauses


def test_detail_retains_four_query_limit_including_auth_and_purchase_read():
    budget = SelectQueryBudget(maximum=4)
    guard_queries(budget)
    clauses = detail_queries(budget)
    assert len(clauses) == 3
    assert "requirement_snapshots" in str(clauses[0])
    assert "requirement_snapshot_items" in str(clauses[1])
    assert "purchase_batches" in str(clauses[2])
    assert budget.business_selects == 4
    assert sum(budget.safety_selects.values()) == 3
    budget.assert_within_budget()


def test_fifth_detail_business_select_fails_original_four_query_limit():
    budget = SelectQueryBudget(maximum=4)
    guard_queries(budget)
    detail_queries(budget)
    record(budget, text("SELECT id FROM suppliers"))
    assert budget.business_selects == 5
    with pytest.raises(AssertionError, match="5 > 4"):
        budget.assert_within_budget()


@pytest.mark.parametrize("query", [
    "SELECT 1", "SELECT current_database()", "SELECT count(*) FROM pg_stat_activity",
    "SELECT * FROM pg_roles", "SELECT * FROM pg_database",
    "SELECT set_config('application_name', 'different', false)",
])
def test_unknown_sql_even_inside_guard_is_not_excluded(query):
    budget = SelectQueryBudget(maximum=3)
    guard_queries(budget, injected_sql=query)
    assert budget.business_selects == 1
    assert sum(budget.safety_selects.values()) == 3


def test_even_identical_sql_outside_actual_guard_is_counted():
    budget = SelectQueryBudget(maximum=3)
    clauses = guard_queries(budget)
    for clause in clauses:
        record(budget, clause)
    assert budget.business_selects == 3
    assert sum(budget.safety_selects.values()) == 3


def test_parameter_values_are_not_stored_or_in_assertion_diagnostics():
    budget = SelectQueryBudget(maximum=0)
    budget.record(None, None, "SELECT :sensitive", {"sensitive": "do-not-log-this"}, None, False)
    with pytest.raises(AssertionError) as caught:
        budget.assert_within_budget()
    assert "do-not-log-this" not in str(caught.value)
    assert "do-not-log-this" not in repr(vars(budget))


def test_counting_does_not_disable_actual_database_identity_rejection():
    budget = SelectQueryBudget(maximum=3)
    with pytest.raises(UnsafeTestDatabase, match="ACTUAL_IDENTITY_MISMATCH"):
        guard_queries(budget, wrong_identity=True)


def test_non_select_commands_remain_outside_original_select_budget():
    budget = SelectQueryBudget(maximum=0)
    budget.record(None, None, "ROLLBACK", None, None, False)
    budget.assert_within_budget()
