from types import SimpleNamespace

import pytest
from alembic.config import Config
from sqlalchemy.engine import make_url

from tests.database_safety import (
    UnsafeTestDatabase, guarded_migration,
    test_database_target as resolve_target,
    validate_database_identity, validate_engine_target, verify_connection,
)


SUFFIX = "0123456789abcdef0123456789abcdef"


def environment(kind="migration"):
    url = (f"postgresql+psycopg://kitchenerp_{kind}_test@127.0.0.1:5432/"
           f"kitchenerp_{kind}_test_{SUFFIX}")
    return {"APP_ENV": "test", "DATABASE_URL": url, "TEST_DATABASE_URL": url,
            f"{kind.upper()}_TEST_DATABASE_URL": url}


def identity(target):
    return dict(database_name=target.url.database, current_role=target.url.username,
                session_role=target.url.username, owner_role=target.url.username,
                server_address="127.0.0.1", server_port=5432, marker=target.marker,
                in_recovery=False, is_superuser=False, can_create_db=False,
                can_create_role=False, can_replicate=False, bypass_rls=False, role_memberships=0)


@pytest.mark.parametrize("kind", ["migration", "regression"])
def test_explicit_disposable_configuration_is_accepted(kind):
    target = resolve_target(kind, environment(kind))
    assert target.kind == kind
    assert target.marker == f"kitchenerp-disposable:{kind}:{SUFFIX}"


@pytest.mark.parametrize("database", ["kitchenerp_prod", "kitchenerp_dev", "kitchenerp_test",
                                     "kitchenerp_migration_test", "kitchenerp_migration_test_backup"])
def test_production_development_shared_and_unapproved_names_are_rejected(database):
    env = environment()
    url = make_url(env["DATABASE_URL"]).set(database=database).render_as_string(hide_password=False)
    env.update(DATABASE_URL=url, TEST_DATABASE_URL=url, MIGRATION_TEST_DATABASE_URL=url)
    with pytest.raises(UnsafeTestDatabase, match="TEST_DB_NAME_REJECTED"):
        resolve_target("migration", env)


@pytest.mark.parametrize("change", [
    {"host": "localhost"}, {"host": "ubuntu.example.invalid"}, {"host": "192.0.2.1"},
    {"host": None}, {"port": None}, {"port": 5433}, {"username": "postgres"},
    {"drivername": "sqlite"}, {"query": {"host": "ubuntu.example.invalid"}},
    {"query": {"options": "-c search_path=other"}},
])
def test_endpoint_role_driver_and_connection_overrides_are_rejected(change):
    env = environment()
    url = make_url(env["DATABASE_URL"])
    # URL.set(None) means retain; create a URL with actual missing fields instead.
    fields = dict(drivername=url.drivername, username=url.username, host=url.host,
                  port=url.port, database=url.database, query=url.query)
    fields.update(change)
    from sqlalchemy.engine import URL
    raw = URL.create(**fields).render_as_string(hide_password=False)
    env.update(DATABASE_URL=raw, TEST_DATABASE_URL=raw, MIGRATION_TEST_DATABASE_URL=raw)
    with pytest.raises(UnsafeTestDatabase):
        resolve_target("migration", env)


@pytest.mark.parametrize("key", ["MIGRATION_TEST_DATABASE_URL", "DATABASE_URL", "TEST_DATABASE_URL", "APP_ENV"])
@pytest.mark.parametrize("value", [None, ""])
def test_missing_or_empty_configuration_never_falls_back_to_dotenv(key, value):
    env = environment()
    if value is None:
        env.pop(key)
    else:
        env[key] = value
    with pytest.raises(UnsafeTestDatabase):
        resolve_target("migration", env)


@pytest.mark.parametrize("key", ["DATABASE_URL", "TEST_DATABASE_URL"])
def test_disagreeing_settings_are_rejected(key):
    env = environment()
    env[key] = environment("regression")["DATABASE_URL"]
    with pytest.raises(UnsafeTestDatabase, match="CONFIGURATION_MISMATCH"):
        resolve_target("migration", env)


@pytest.mark.parametrize("key", ["PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER",
                                 "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS"])
def test_libpq_environment_overrides_are_rejected(key):
    env = environment()
    env[key] = "unapproved"
    with pytest.raises(UnsafeTestDatabase, match="LIBPQ_OVERRIDE_REJECTED"):
        resolve_target("migration", env)


@pytest.mark.parametrize("change", [
    {"database_name": "kitchenerp_test"}, {"server_address": "192.0.2.1"},
    {"server_port": 5433}, {"current_role": "postgres"}, {"session_role": "postgres"},
    {"owner_role": "postgres"}, {"marker": None}, {"in_recovery": True},
    {"is_superuser": True}, {"can_create_db": True}, {"can_create_role": True},
    {"can_replicate": True}, {"bypass_rls": True}, {"role_memberships": 1},
])
def test_actual_connection_identity_and_isolation_are_checked(change):
    target = resolve_target("migration", environment())
    actual = identity(target)
    actual.update(change)
    with pytest.raises(UnsafeTestDatabase):
        validate_database_identity(target, actual, 0)


def test_actual_valid_identity_requires_no_other_application_sessions():
    target = resolve_target("migration", environment())
    validate_database_identity(target, identity(target), 0)
    with pytest.raises(UnsafeTestDatabase, match="TEST_DB_IN_USE"):
        validate_database_identity(target, identity(target), 1)


def test_disabled_database_and_mismatching_engine_never_connect():
    target = resolve_target("migration", environment())
    with pytest.raises(UnsafeTestDatabase, match="ACCESS_DISABLED"):
        validate_engine_target(None, target.url)
    with pytest.raises(UnsafeTestDatabase, match="ENGINE_MISMATCH"):
        validate_engine_target(target, target.url.set(database="kitchenerp_test"))


@pytest.mark.parametrize("kind", [None, "regression"])
@pytest.mark.parametrize("operation", ["upgrade", "downgrade"])
def test_migration_commands_are_never_invoked_without_migration_target(kind, operation):
    calls = []
    env = environment(kind or "migration")
    target = resolve_target(kind, env) if kind else None
    with pytest.raises(UnsafeTestDatabase, match="MIGRATION_TEST_DATABASE_REQUIRED"):
        guarded_migration(operation, lambda *a, **k: calls.append(a), target, env, Config(), "base")
    assert calls == []


@pytest.mark.parametrize("mismatch", ["environment", "config_url", "config_connection"])
def test_migration_configuration_changes_fail_before_invoking_downgrade(mismatch):
    env = environment()
    target = resolve_target("migration", env)
    config = Config()
    if mismatch == "environment":
        env["DATABASE_URL"] = environment("regression")["DATABASE_URL"]
    elif mismatch == "config_url":
        config.set_main_option("sqlalchemy.url", environment("regression")["DATABASE_URL"])
    else:
        config.attributes["connection"] = object()
    calls = []
    with pytest.raises(UnsafeTestDatabase):
        guarded_migration("downgrade", lambda *a, **k: calls.append(a), target, env, config, "base")
    assert calls == []


def test_valid_configuration_only_allows_further_connection_verification():
    env = environment()
    target = resolve_target("migration", env)
    calls = []
    config = Config()
    guarded_migration("downgrade", lambda *a, **k: calls.append(a), target, env, config, "base")
    assert calls == [(config, "base")]


def test_connection_verification_reads_actual_identity_before_session_setup():
    target = resolve_target("migration", environment())
    events = []

    class Connection:
        def execute(self, statement, params=None):
            events.append("session" if "set_config" in str(statement) else "identity")
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: identity(target)))

        def scalar(self, statement, params):
            events.append("other_sessions")
            return 0

        def rollback(self):
            events.append("rollback")

        def commit(self):
            events.append("commit")

    verify_connection(Connection(), target, "test-process")
    assert events == ["identity", "other_sessions", "rollback", "session", "commit"]


def test_actual_mismatch_stops_before_any_session_mutation():
    target = resolve_target("migration", environment())
    actual = identity(target) | {"database_name": "kitchenerp_test"}
    calls = []
    connection = SimpleNamespace(
        execute=lambda *a, **k: SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: actual)),
        scalar=lambda *a, **k: 0, rollback=lambda: calls.append("rollback"),
        commit=lambda: calls.append("commit"),
    )
    with pytest.raises(UnsafeTestDatabase):
        verify_connection(connection, target, "test-process")
    assert calls == []


@pytest.fixture
def database_disabled_guard():
    from tests import conftest
    config = SimpleNamespace(getoption=lambda name: False)
    conftest.pytest_configure(config)
    try:
        yield
    finally:
        conftest.pytest_unconfigure(config)


def test_pytest_connection_guard_blocks_all_real_database_access_by_default(database_disabled_guard):
    from sqlalchemy import create_engine
    engine = create_engine("postgresql+psycopg://unused@127.0.0.1:5432/kitchenerp_test")
    try:
        with pytest.raises(UnsafeTestDatabase, match="TEST_DB_ACCESS_DISABLED"):
            engine.connect()
    finally:
        engine.dispose()


def test_pytest_alembic_guard_blocks_both_commands_before_env_py(database_disabled_guard):
    from alembic import command
    for operation in (command.upgrade, command.downgrade):
        with pytest.raises(UnsafeTestDatabase, match="MIGRATION_TEST_DATABASE_REQUIRED"):
            operation(Config(), "base")


@pytest.mark.parametrize("verified", [True, False])
def test_pytest_migration_preflight_precedes_alembic_and_failure_never_enters_it(monkeypatch, verified):
    from alembic import command
    from app.core.config import settings
    from tests import conftest
    env = environment()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(settings, "database_url", env["DATABASE_URL"])
    monkeypatch.setattr(settings, "test_database_url", env["TEST_DATABASE_URL"])
    events = []

    class Probe:
        def connect(self):
            events.append("verify-actual-connection")
            if not verified:
                raise UnsafeTestDatabase("TEST_DB_ACTUAL_IDENTITY_MISMATCH")
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("close")

        def dispose(self):
            events.append("dispose")

    monkeypatch.setattr(conftest, "create_engine", lambda *a, **k: Probe())
    monkeypatch.setattr(command, "downgrade", lambda *a, **k: events.append("alembic-downgrade"))
    config = SimpleNamespace(getoption=lambda name: name == "--migration-tests")
    conftest.pytest_configure(config)
    try:
        if verified:
            command.downgrade(Config(), "base")
            assert events == ["verify-actual-connection", "alembic-downgrade", "close", "dispose"]
        else:
            with pytest.raises(UnsafeTestDatabase):
                command.downgrade(Config(), "base")
            assert events == ["verify-actual-connection", "dispose"]
    finally:
        conftest.pytest_unconfigure(config)


def test_mode_switching_in_one_process_is_rejected():
    from tests import conftest
    with pytest.raises(pytest.UsageError, match="separate pytest processes"):
        conftest.pytest_configure(SimpleNamespace(getoption=lambda name: True))


def test_actual_connection_failure_closes_connection_without_entering_test_sql(monkeypatch):
    from sqlalchemy.engine import Engine
    from tests import conftest
    env = environment()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS"):
        monkeypatch.delenv(key, raising=False)
    events = []
    connection = SimpleNamespace(close=lambda: events.append("close"))
    monkeypatch.setattr(Engine, "connect", lambda *a, **k: connection)

    def failed_identity(*args):
        events.append("identity-rejected")
        raise UnsafeTestDatabase("TEST_DB_ISOLATION_NOT_VERIFIED")

    monkeypatch.setattr(conftest, "verify_connection", failed_identity)
    config = SimpleNamespace(getoption=lambda name: name == "--migration-tests")
    conftest.pytest_configure(config)
    try:
        with pytest.raises(UnsafeTestDatabase, match="CONNECTION_NOT_VERIFIED"):
            Engine.connect(SimpleNamespace(url=make_url(env["DATABASE_URL"])))
        assert events == ["identity-rejected", "close"]
    finally:
        conftest.pytest_unconfigure(config)
