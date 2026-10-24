"""Fail-closed policy for *pre-provisioned* disposable PostgreSQL test databases.

This module never provisions, migrates, or cleans a database. Error messages are
fixed codes: connection strings and driver exceptions must not reach test output.
"""

from dataclasses import dataclass
import re
from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url


class UnsafeTestDatabase(RuntimeError):
    pass


@dataclass(frozen=True)
class TestDatabaseTarget:
    kind: str
    url: URL
    marker: str


def test_database_target(kind: str, environ: Mapping[str, str]) -> TestDatabaseTarget:
    if kind not in {"migration", "regression"}:
        raise UnsafeTestDatabase("TEST_DB_INVALID_MODE")
    key = f"{kind.upper()}_TEST_DATABASE_URL"
    raw = environ.get(key)
    if not raw or environ.get("APP_ENV") != "test":
        raise UnsafeTestDatabase("TEST_DB_EXPLICIT_CONFIGURATION_REQUIRED")
    try:
        url = make_url(raw)
        database_url = make_url(environ["DATABASE_URL"])
        test_url = make_url(environ["TEST_DATABASE_URL"])
    except Exception:
        raise UnsafeTestDatabase("TEST_DB_EXPLICIT_CONFIGURATION_REQUIRED") from None
    if url != database_url or url != test_url:
        raise UnsafeTestDatabase("TEST_DB_CONFIGURATION_MISMATCH")
    if url.drivername != "postgresql+psycopg" or url.query:
        raise UnsafeTestDatabase("TEST_DB_DRIVER_OR_OPTIONS_REJECTED")
    if url.host != "127.0.0.1" or url.port != 5432:
        raise UnsafeTestDatabase("TEST_DB_ENDPOINT_REJECTED")
    prefix = f"kitchenerp_{kind}_test_"
    if not re.fullmatch(re.escape(prefix) + r"[0-9a-f]{32}", url.database or ""):
        raise UnsafeTestDatabase("TEST_DB_NAME_REJECTED")
    if url.username != f"kitchenerp_{kind}_test":
        raise UnsafeTestDatabase("TEST_DB_ROLE_REJECTED")
    if any(environ.get(name) for name in (
        "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE",
        "PGSERVICEFILE", "PGOPTIONS",
    )):
        raise UnsafeTestDatabase("TEST_DB_LIBPQ_OVERRIDE_REJECTED")
    return TestDatabaseTarget(kind, url, f"kitchenerp-disposable:{kind}:{url.database[len(prefix):]}")


def validate_engine_target(target: TestDatabaseTarget | None, url: URL) -> None:
    if target is None:
        raise UnsafeTestDatabase("TEST_DB_ACCESS_DISABLED")
    if url != target.url:
        raise UnsafeTestDatabase("TEST_DB_ENGINE_MISMATCH")


def validate_database_identity(target: TestDatabaseTarget, actual: Mapping, active_others: int) -> None:
    if (actual["database_name"] != target.url.database
            or actual["server_address"] != "127.0.0.1"
            or actual["server_port"] != 5432
            or actual["current_role"] != target.url.username
            or actual["session_role"] != target.url.username
            or actual["owner_role"] != target.url.username):
        raise UnsafeTestDatabase("TEST_DB_ACTUAL_IDENTITY_MISMATCH")
    if (actual["marker"] != target.marker or actual["in_recovery"]
            or any(actual[name] for name in (
                "is_superuser", "can_create_db", "can_create_role", "can_replicate",
                "bypass_rls", "role_memberships",
            ))):
        raise UnsafeTestDatabase("TEST_DB_ISOLATION_NOT_VERIFIED")
    if active_others:
        raise UnsafeTestDatabase("TEST_DB_IN_USE")


def verify_connection(connection, target: TestDatabaseTarget, application_name: str) -> None:
    actual = connection.execute(text("""
        SELECT current_database() AS database_name, current_user AS current_role,
               session_user AS session_role, host(inet_server_addr()) AS server_address,
               inet_server_port() AS server_port, pg_is_in_recovery() AS in_recovery,
               pg_get_userbyid(d.datdba) AS owner_role,
               shobj_description(d.oid, 'pg_database') AS marker,
               r.rolsuper AS is_superuser, r.rolcreatedb AS can_create_db,
               r.rolcreaterole AS can_create_role, r.rolreplication AS can_replicate,
               r.rolbypassrls AS bypass_rls,
               (SELECT count(*) FROM pg_auth_members WHERE member = r.oid) AS role_memberships
        FROM pg_database d JOIN pg_roles r ON r.rolname = current_user
        WHERE d.datname = current_database()
    """)).mappings().one()
    active_others = connection.scalar(text("""
        SELECT count(*) FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
          AND application_name IS DISTINCT FROM :application_name
    """), {"application_name": application_name})
    validate_database_identity(target, actual, active_others)
    # Identity checks are read-only. Do not return an implicit open transaction.
    connection.rollback()
    connection.execute(text("SELECT set_config('application_name', :name, false)"),
                       {"name": application_name})
    connection.commit()


def guarded_migration(operation: str, invoke, target: TestDatabaseTarget | None,
                      environ: Mapping[str, str], config, *args, **kwargs):
    if target is None or target.kind != "migration":
        raise UnsafeTestDatabase("MIGRATION_TEST_DATABASE_REQUIRED")
    if test_database_target("migration", environ) != target:
        raise UnsafeTestDatabase("TEST_DB_CONFIGURATION_CHANGED")
    # env.py uses settings.database_url, not sqlalchemy.url; reject alternate
    # connections/URLs rather than pretending a Config URL selects the database.
    if config.attributes.get("connection") is not None:
        raise UnsafeTestDatabase("TEST_DB_CONFIG_CONNECTION_REJECTED")
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        try:
            validate_engine_target(target, make_url(configured_url))
        except Exception:
            raise UnsafeTestDatabase("TEST_DB_CONFIG_URL_REJECTED") from None
    if operation not in {"upgrade", "downgrade"}:
        raise UnsafeTestDatabase("TEST_DB_MIGRATION_OPERATION_REJECTED")
    return invoke(config, *args, **kwargs)
