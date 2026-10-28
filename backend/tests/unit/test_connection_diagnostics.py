"""Exercise the real guard with fake IO, never opening a PostgreSQL connection."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import InvalidRequestError, OperationalError, TimeoutError
from sqlalchemy.pool import QueuePool

from tests.connection_diagnostics import ConnectionDiagnostic, open_verified_connection
from tests.database_safety import UnsafeTestDatabase
from tests.unit.test_database_safety import environment, identity, resolve_target


SECRET = "DO_NOT_LOG_driver_password_token_patient_or_sql_parameters"


class Connection:
    def __init__(self, target, *, changes=None, others=0, fail=None, error=None, close_error=False):
        self.actual = {**identity(target), **(changes or {})}
        self.others = others
        self.fail = fail
        self.error = error or OperationalError(SECRET, {SECRET: SECRET}, RuntimeError(SECRET))
        self.close_error = close_error
        self.calls = []
        self.transaction = False
        self.closed = False
        self.application_name = None

    def step(self, phase):
        self.calls.append(phase)
        if self.fail == phase:
            raise self.error

    def execute(self, statement, parameters=None):
        phase = "application_name" if parameters is not None else "identity_query"
        self.step(phase)
        self.transaction = True
        if phase == "application_name":
            self.application_name = parameters["name"]
        return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: self.actual))

    def scalar(self, statement, parameters):
        self.step("competing_sessions_query")
        self.transaction = True
        assert parameters == {"application_name": "offline-process"}
        return self.others

    def rollback(self):
        self.step("rollback")
        self.transaction = False

    def commit(self):
        self.step("commit")
        self.transaction = False

    def close(self):
        self.calls.append("close")
        self.closed = True
        self.transaction = False
        if self.close_error:
            raise RuntimeError(SECRET)


def target():
    return resolve_target("regression", environment("regression"))


def open_fake(connection, database_target):
    return open_verified_connection(lambda engine: connection, object(), database_target, "offline-process")


def test_success_preserves_sql_order_and_returns_original_connection_without_open_transaction(caplog):
    database_target = target()
    connection = Connection(database_target)
    assert open_fake(connection, database_target) is connection
    assert connection.calls == ["identity_query", "competing_sessions_query", "rollback", "application_name", "commit"]
    assert connection.application_name == "offline-process"
    assert not connection.transaction and not connection.closed
    assert not caplog.records


@pytest.mark.parametrize("changes,reason", [
    ({"database_name": "wrong"}, "TEST_DB_ACTUAL_IDENTITY_MISMATCH"),
    ({"current_role": "wrong"}, "TEST_DB_ACTUAL_IDENTITY_MISMATCH"),
    ({"session_role": "wrong"}, "TEST_DB_ACTUAL_IDENTITY_MISMATCH"),
    ({"owner_role": "wrong"}, "TEST_DB_ACTUAL_IDENTITY_MISMATCH"),
    ({"server_address": "::1"}, "TEST_DB_ACTUAL_IDENTITY_MISMATCH"),
    ({"server_port": 5433}, "TEST_DB_ACTUAL_IDENTITY_MISMATCH"),
    ({"marker": "wrong"}, "TEST_DB_ISOLATION_NOT_VERIFIED"),
    ({"is_superuser": True}, "TEST_DB_ISOLATION_NOT_VERIFIED"),
    ({"role_memberships": 1}, "TEST_DB_ISOLATION_NOT_VERIFIED"),
    ({"in_recovery": True}, "TEST_DB_ISOLATION_NOT_VERIFIED"),
])
def test_identity_role_marker_and_privilege_rejections_remain_fail_closed(changes, reason, caplog):
    database_target = target()
    connection = Connection(database_target, changes=changes)
    with pytest.raises(UnsafeTestDatabase, match="^TEST_DB_CONNECTION_NOT_VERIFIED$"):
        open_fake(connection, database_target)
    assert connection.closed
    assert "commit" not in connection.calls
    assert f"phase=identity_validation reason={reason}" in caplog.text


def test_other_application_session_is_rejected_not_adopted(caplog):
    database_target = target()
    connection = Connection(database_target, others=1)
    with pytest.raises(UnsafeTestDatabase):
        open_fake(connection, database_target)
    assert connection.closed and connection.application_name is None
    assert "phase=identity_validation reason=TEST_DB_IN_USE" in caplog.text


@pytest.mark.parametrize("phase", ["identity_query", "competing_sessions_query", "rollback", "application_name", "commit"])
def test_exact_failed_operation_is_reported_without_driver_details(phase, caplog):
    database_target = target()
    connection = Connection(database_target, fail=phase)
    with pytest.raises(UnsafeTestDatabase) as caught:
        open_fake(connection, database_target)
    assert connection.closed and not connection.transaction
    assert f"phase={phase} reason=DRIVER_OPERATION_ERROR" in caplog.text
    assert SECRET not in caplog.text + str(caught.value)


@pytest.mark.parametrize("error,reason", [
    (OperationalError(SECRET, {SECRET: SECRET}, RuntimeError(SECRET)), "DRIVER_CONNECTION_ERROR"),
    (TimeoutError(SECRET), "POOL_TIMEOUT"),
    (RuntimeError(SECRET), "UNEXPECTED_ERROR"),
])
def test_connect_failure_still_rejected_and_not_leaked(error, reason, caplog):
    def fail(engine):
        raise error
    with pytest.raises(UnsafeTestDatabase):
        open_verified_connection(fail, object(), target(), "offline-process")
    assert f"phase=connect reason={reason}" in caplog.text
    assert SECRET not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_transaction_error_has_distinct_fixed_category(caplog):
    database_target = target()
    connection = Connection(database_target, fail="commit", error=InvalidRequestError(SECRET))
    with pytest.raises(UnsafeTestDatabase):
        open_fake(connection, database_target)
    assert "phase=commit reason=TRANSACTION_STATE_ERROR" in caplog.text
    assert SECRET not in caplog.text


def test_close_failure_and_later_cleanup_failure_do_not_erase_original_diagnostic(caplog):
    database_target = target()
    api_connection = Connection(database_target, others=1, close_error=True)
    with pytest.raises(UnsafeTestDatabase, match="^TEST_DB_CONNECTION_NOT_VERIFIED$"):
        open_fake(api_connection, database_target)
    cleanup_connection = Connection(database_target, fail="identity_query")
    with pytest.raises(UnsafeTestDatabase):
        open_fake(cleanup_connection, database_target)
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "TEST_DB_DIAGNOSTIC phase=identity_validation reason=TEST_DB_IN_USE",
        "TEST_DB_DIAGNOSTIC phase=close reason=UNEXPECTED_ERROR",
        "TEST_DB_DIAGNOSTIC phase=identity_query reason=DRIVER_OPERATION_ERROR",
    ]
    assert SECRET not in caplog.text


def test_repeated_checkouts_keep_application_tag_and_leave_no_guard_transaction():
    database_target = target()
    for _ in range(4):
        connection = Connection(database_target)
        open_fake(connection, database_target)
        assert not connection.transaction
        # Simulated caller transaction and release, not a claim about a real pool.
        connection.transaction = True
        connection.rollback()
        connection.close()
        assert connection.closed and not connection.transaction
        assert connection.application_name == "offline-process"


@pytest.mark.parametrize("others", [0, 1])
def test_real_queue_pool_returns_all_leases_without_any_database_io(others):
    database_target = target()
    created = []

    def creator():
        connection = Connection(database_target, others=others)
        created.append(connection)
        return connection

    pool = QueuePool(creator, pool_size=1, max_overflow=0)
    try:
        for _ in range(4):
            if others:
                with pytest.raises(UnsafeTestDatabase):
                    open_verified_connection(lambda engine: pool.connect(), object(), database_target, "offline-process")
            else:
                connection = open_verified_connection(lambda engine: pool.connect(), object(), database_target, "offline-process")
                assert not connection.transaction
                connection.close()
            assert pool.checkedout() == 0
        assert len(created) == 1  # One expected idle pooled connection, no extra lease.
    finally:
        pool.dispose()
    assert created[0].closed


@pytest.mark.parametrize("others", [0, 1])
def test_diagnostic_context_is_reset_after_success_and_rejection(others):
    from tests.connection_diagnostics import _CURRENT
    database_target = target()
    connection = Connection(database_target, others=others)
    if others:
        with pytest.raises(UnsafeTestDatabase):
            open_fake(connection, database_target)
    else:
        open_fake(connection, database_target)
        connection.close()
    assert _CURRENT.get() is None


def test_logger_failure_cannot_change_guard_result(monkeypatch):
    from tests import connection_diagnostics
    def broken(*args, **kwargs):
        raise RuntimeError(SECRET)
    monkeypatch.setattr(connection_diagnostics._LOG, "error", broken)
    database_target = target()
    connection = Connection(database_target, others=1)
    with pytest.raises(UnsafeTestDatabase, match="^TEST_DB_CONNECTION_NOT_VERIFIED$"):
        open_fake(connection, database_target)
    assert connection.closed


def test_unknown_stage_and_guard_error_cannot_inject_log_content(caplog):
    diagnostic = ConnectionDiagnostic()
    diagnostic.stage(SECRET)
    diagnostic.failure(UnsafeTestDatabase(SECRET))
    assert "phase=unknown reason=GUARD_REJECTED" in caplog.text
    assert SECRET not in caplog.text


def test_conftest_keeps_preconnection_target_and_environment_checks():
    path = Path(__file__).resolve().parents[1] / "conftest.py"
    configure = next(n for n in ast.parse(path.read_text(encoding="utf8")).body
                     if isinstance(n, ast.FunctionDef) and n.name == "pytest_configure")
    connect = next(n for n in configure.body if isinstance(n, ast.FunctionDef) and n.name == "safe_connect")
    assert isinstance(connect.body[0], ast.Expr)
    assert connect.body[0].value.func.id == "validate_engine_target"
    assert isinstance(connect.body[1], ast.If)
    assert connect.body[1].test.left.func.id == "test_database_target"
    assert any(isinstance(n, ast.Raise) for n in ast.walk(connect.body[1]))
    assert isinstance(connect.body[2], ast.Return)
    assert connect.body[2].value.func.id == "open_verified_connection"
