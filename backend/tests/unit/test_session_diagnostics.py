"""Session/lifecycle diagnostics with fake DBAPI connections and real pool events."""

from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine, URL
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.pool import QueuePool

from tests import session_diagnostics
from tests.connection_diagnostics import open_verified_connection
from tests.database_safety import UnsafeTestDatabase
from tests.session_diagnostics import SessionTrace, _PEERS
from tests.unit.test_connection_diagnostics import Connection, SECRET, target


class PeerConnection(Connection):
    def __init__(self, database_target, *, peers=(), broken=False, **kwargs):
        super().__init__(database_target, **kwargs)
        self.peers = peers
        self.broken = broken
        self.peer_queries = 0

    def execute(self, statement, parameters=None):
        if statement is _PEERS:
            self.peer_queries += 1
            assert parameters == {"expected": "offline-process"}
            if self.broken:
                raise RuntimeError(SECRET)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.peers))
        return super().execute(statement, parameters)


@pytest.fixture
def trace(monkeypatch):
    tracer = SessionTrace()
    monkeypatch.setattr(session_diagnostics, "_ACTIVE", tracer)
    tracer.context("tests/fake_test.py::test_case[" + SECRET + "]", "call")
    yield tracer
    tracer.close()


def open_fake(connection, database_target):
    return open_verified_connection(lambda engine: connection, object(), database_target, "offline-process")


@pytest.mark.parametrize("app", ["blank", "other"])
def test_unrecognized_session_is_still_rejected_and_classified(trace, caplog, app):
    database_target = target()
    connection = PeerConnection(database_target, others=1,
                                peers=[dict(pid=9283746, app_class=app, state_class="idle")])
    with pytest.raises(UnsafeTestDatabase, match="^TEST_DB_CONNECTION_NOT_VERIFIED$"):
        open_fake(connection, database_target)
    assert connection.closed and connection.peer_queries == 1
    assert "reason=TEST_DB_IN_USE" in caplog.text
    assert f"app={app} state=idle tracked=no" in caplog.text
    assert "guard_other_count=1" in caplog.text
    assert "phase=call" in caplog.text
    assert "9283746" not in caplog.text and SECRET not in caplog.text


def test_success_has_no_extra_sql_and_expected_tag_does_not_grant_unknown_peers_access(trace, caplog):
    database_target = target()
    connection = PeerConnection(database_target, others=0)
    open_fake(connection, database_target)
    assert connection.peer_queries == 0 and not caplog.records
    # Expected-tag peers may coexist, but a separate other-tag peer still rejects.
    rejected = PeerConnection(database_target, others=1, peers=[
        dict(pid=1, app_class="expected", state_class="active"),
        dict(pid=2, app_class="other", state_class="idle_transaction"),
    ])
    with pytest.raises(UnsafeTestDatabase):
        open_fake(rejected, database_target)
    assert "app=expected state=active" in caplog.text
    assert "app=other state=idle_transaction" in caplog.text


@pytest.mark.parametrize("state", ["active", "idle", "idle_transaction", SECRET])
def test_state_categories_are_whitelisted_and_never_echo_unknown_content(trace, caplog, state):
    database_target = target()
    connection = PeerConnection(database_target, others=1,
                                peers=[dict(pid=1, app_class="blank", state_class=state)])
    with pytest.raises(UnsafeTestDatabase):
        open_fake(connection, database_target)
    expected = state if state != SECRET else "other"
    assert f"state={expected}" in caplog.text and SECRET not in caplog.text


def test_bad_identity_never_runs_session_diagnostic_query(trace, caplog):
    database_target = target()
    connection = PeerConnection(database_target, changes={"marker": SECRET}, others=1)
    with pytest.raises(UnsafeTestDatabase):
        open_fake(connection, database_target)
    assert connection.closed and connection.peer_queries == 0
    assert "TEST_DB_ISOLATION_NOT_VERIFIED" in caplog.text and SECRET not in caplog.text


def test_failed_diagnostic_query_cannot_replace_or_bypass_rejection(trace, caplog):
    database_target = target()
    connection = PeerConnection(database_target, others=1, broken=True)
    with pytest.raises(UnsafeTestDatabase, match="^TEST_DB_CONNECTION_NOT_VERIFIED$"):
        open_fake(connection, database_target)
    assert connection.closed and connection.peer_queries == 1
    assert "TEST_DB_SESSION_DETAIL_UNAVAILABLE" in caplog.text
    assert "reason=TEST_DB_IN_USE" in caplog.text and SECRET not in caplog.text


def test_broken_tracer_never_skips_guard(trace, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError(SECRET)
    monkeypatch.setattr(trace, "instrument", broken)
    monkeypatch.setattr(trace, "rejected", broken)
    database_target = target()
    connection = PeerConnection(database_target, others=1)
    with pytest.raises(UnsafeTestDatabase, match="^TEST_DB_CONNECTION_NOT_VERIFIED$"):
        open_fake(connection, database_target)
    assert connection.closed


def fake_engine(database_target):
    created = []
    def creator():
        connection = PeerConnection(database_target)
        connection.info = SimpleNamespace(backend_pid=9283746 + len(created))
        created.append(connection)
        return connection
    pool = QueuePool(creator, pool_size=2, max_overflow=0)
    engine = Engine(pool, DefaultDialect(), URL.create("postgresql"))
    return engine, created


def test_two_real_pool_connections_correlate_creation_checkout_checkin_close_and_dispose(trace, caplog):
    database_target = target()
    engine, created = fake_engine(database_target)
    trace.instrument(engine)
    first = engine.raw_connection()
    second = engine.raw_connection()
    assert engine.pool.checkedout() == 2 and len(created) == 2
    trace.verified(SimpleNamespace(_dbapi_connection=SimpleNamespace(driver_connection=created[0])))
    first.close()
    assert engine.pool.checkedout() == 1
    trace.context("tests/fake_test.py::test_later", "teardown")
    rejected = PeerConnection(database_target, others=1, peers=[
        dict(pid=9283746, app_class="blank", state_class="idle"),
        dict(pid=9283747, app_class="other", state_class="idle_transaction"),
    ])
    with pytest.raises(UnsafeTestDatabase):
        open_fake(rejected, database_target)
    assert "tracked=yes engine=e1 connection=c1" in caplog.text
    assert "ever_verified=yes last=checkin" in caplog.text
    assert "tracked=yes engine=e1 connection=c2" in caplog.text
    assert "ever_verified=no last=checkout" in caplog.text
    assert "phase=teardown" in caplog.text
    assert all("928374" not in record.getMessage() for record in caplog.records)
    second.close()
    engine.dispose()
    names = [item["event"] for item in trace.events]
    assert names.count("connect") == names.count("checkout") == names.count("checkin") == names.count("close") == 2
    assert names.count("dispose") == 1
    assert all(connection.closed for connection in created)


def test_closed_backend_is_not_misattributed_to_later_peer(trace, caplog):
    database_target = target()
    engine, _ = fake_engine(database_target)
    trace.instrument(engine)
    connection = engine.raw_connection()
    connection.close()
    engine.dispose()
    trace.rejected(PeerConnection(database_target, peers=[
        dict(pid=9283746, app_class="other", state_class="idle"),
    ]), "offline-process", 1)
    assert "tracked=no engine=unknown" in caplog.text


def test_trace_removal_does_not_close_pool_or_change_settings(trace):
    engine, created = fake_engine(target())
    trace.instrument(engine)
    connection = engine.raw_connection()
    connection.close()
    assert engine.pool.size() == 2 and not created[0].closed
    trace.close()
    assert not created[0].closed
    engine.dispose()


def test_trace_removal_after_engine_dispose_does_not_leave_listeners_on_recreated_pool(trace):
    engine, _ = fake_engine(target())
    trace.instrument(engine)
    engine.raw_connection().close()
    engine.dispose()
    trace.close()
    count = len(trace.events)
    engine.raw_connection().close()
    engine.dispose()
    assert len(trace.events) == count


def test_peer_sql_returns_only_categories_and_internal_correlation_not_raw_sensitive_fields():
    sql = str(_PEERS)
    assert "application_name = :expected" in sql
    assert "application_name IS NULL OR btrim(application_name) = ''" in sql
    assert "ELSE 'other' END AS app_class" in sql
    assert "datname = current_database() AND pid <> pg_backend_pid()" in sql
    assert "SELECT pid," in sql
    assert all(field not in sql for field in ["query,", "client_addr", "usename", "SELECT application_name"])


@pytest.mark.parametrize("others", [0, 1])
def test_extra_diagnostic_sql_is_only_after_rejection_and_is_not_excluded_from_budget(trace, others):
    from tests.query_budget import SelectQueryBudget
    from tests.unit.snapshots.test_query_budget import record
    budget = SelectQueryBudget(maximum=3)

    class Counted(PeerConnection):
        def execute(self, statement, parameters=None):
            record(budget, statement)
            return super().execute(statement, parameters)

        def scalar(self, statement, parameters):
            record(budget, statement)
            return super().scalar(statement, parameters)

    database_target = target()
    connection = Counted(database_target, others=others)
    if others:
        with pytest.raises(UnsafeTestDatabase):
            open_fake(connection, database_target)
        assert connection.peer_queries == 1
        assert budget.business_selects == 1  # Diagnostic SQL remains an ordinary SELECT.
        assert sum(budget.safety_selects.values()) == 2
    else:
        open_fake(connection, database_target)
        assert connection.peer_queries == budget.business_selects == 0
        assert sum(budget.safety_selects.values()) == 3


def test_interleaved_unmarked_connection_window_reproduces_rejection_without_proving_ci_cause(trace, caplog):
    database_target = target()
    # Model two physical sessions created before either guard finishes tagging.
    tags = {1: "", 2: ""}

    class Pending(PeerConnection):
        def __init__(self, pid):
            super().__init__(database_target, peers=[dict(pid=2, app_class="blank", state_class="idle")])
            self.pid = pid

        def scalar(self, statement, parameters):
            self.step("competing_sessions_query")
            return sum(tag != parameters["application_name"] for pid, tag in tags.items() if pid != self.pid)

        def execute(self, statement, parameters=None):
            result = super().execute(statement, parameters)
            if parameters and "name" in parameters:
                tags[self.pid] = parameters["name"]
            return result

        def close(self):
            super().close()
            tags.pop(self.pid, None)

    first, second = Pending(1), Pending(2)
    with pytest.raises(UnsafeTestDatabase):
        open_fake(first, database_target)
    assert "reason=TEST_DB_IN_USE" in caplog.text and "app=blank" in caplog.text
    assert first.application_name is None and first.closed
    open_fake(second, database_target)
    assert tags == {2: "offline-process"}
    second.close()
