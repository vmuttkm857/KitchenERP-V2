"""CI-only provisioning/initialization; pytest's existing guards stay unchanged.

Never run against a developer or production server. The administrator uses peer
authentication on the new cluster's private socket. Alembic uses a separate,
non-admin initializer with rights only in the approved empty regression DB.
"""
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from tests.database_safety import (  # noqa: E402
    test_database_target, validate_engine_target, verify_connection,
)

ROLE = "kitchenerp_regression_test"
INITIALIZER = "kitchenerp_ci_initializer"
URL_KEYS = ("REGRESSION_TEST_DATABASE_URL", "DATABASE_URL", "TEST_DATABASE_URL")
BATCHES = {
    "h01": ["tests/api/requirements/test_confirmed_adjustment_coverage_api.py"],
    "h07": ["tests/api/snapshots/test_snapshot_result_consistency_api.py"],
    "modules": ["tests/api/snapshots", "tests/api/order_adjustments", "tests/api/exports", "tests/api/purchases"],
    "full": ["tests/api", "tests/integration", "tests/regression"],
}


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def context():
    require(sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "CI_HOST_REQUIRED")
    require(Path.cwd() == BACKEND, "CI_BACKEND_DIRECTORY_REQUIRED")
    name = os.environ.get("CI_APPROVED_DATABASE", "")
    require(re.fullmatch(r"kitchenerp_regression_test_[0-9a-f]{32}", name), "CI_EXACT_DB_APPROVAL_REQUIRED")
    run, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(run.isdecimal() and attempt.isdecimal(), "CI_RUN_ID_REQUIRED")
    cluster = Path(f"/tmp/kitchenerp-ci-{run}-{attempt}")
    require(os.environ.get("CI_PG_CLUSTER") == str(cluster), "CI_CLUSTER_MISMATCH")
    require(not any(os.environ.get(key) for key in (
        "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE",
        "PGSERVICEFILE", "PGOPTIONS", "PGPASSWORD", "PGPASSFILE", "MIGRATION_TEST_DATABASE_URL",
        "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_XDIST_WORKER",
    )), "CI_CONNECTION_OVERRIDE_REJECTED")
    require(os.environ.get("APP_ENV") == "test", "CI_TEST_ENV_REQUIRED")
    require(not (BACKEND / ".env").exists(), "CI_DOTENV_REJECTED")
    return name, cluster


def admin(sql, database="postgres"):
    name, cluster = context()
    require(database in {"postgres", name}, "CI_ADMIN_DATABASE_REJECTED")
    result = subprocess.run([
        "sudo", "-n", "-u", "postgres", "/usr/lib/postgresql/17/bin/psql",
        "-X", "--no-password", "-v", "ON_ERROR_STOP=1", "-At",
        "-h", str(cluster / "socket"), "-p", "5432", "-U", "postgres", "-d", database,
    ], input=sql, text=True, capture_output=True)
    # Never echo failed SQL or driver errors: CREATE ROLE includes a password.
    require(result.returncode == 0, "CI_ADMIN_OPERATION_FAILED")
    return result.stdout.strip()


def mask(value):
    print(f"::add-mask::{value}", flush=True)


def configure_urls(url):
    raw = url.render_as_string(hide_password=False)
    for key in URL_KEYS:
        os.environ[key] = raw
    return raw


@contextmanager
def guarded_connections(url, verify):
    """Every Alembic-created SQLAlchemy connection is checked before any DDL."""
    original = Engine.connect

    def connect(engine, *args, **kwargs):
        require(engine.url == url, "CI_ENGINE_TARGET_REJECTED")
        require(all(make_url(os.environ[key]) == url for key in URL_KEYS), "CI_URL_CHANGED")
        connection = original(engine, *args, **kwargs)
        try:
            verify(connection)
        except Exception:
            connection.close()
            raise
        return connection

    Engine.connect = connect
    try:
        yield
    finally:
        Engine.connect = original


def verify_initializer(connection, name, cluster):
    row = connection.execute(text("""
        SELECT current_database(), current_user, session_user, host(inet_server_addr()),
               inet_server_port(), current_setting('server_version_num')::int,
               pg_get_userbyid(d.datdba), shobj_description(d.oid,'pg_database'),
               r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls,
               (SELECT count(*) FROM pg_auth_members WHERE member=r.oid),
               pg_is_in_recovery()
        FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
        WHERE d.datname=current_database()
    """)).one()
    require(tuple(row[:5]) == (name, INITIALIZER, INITIALIZER, "127.0.0.1", 5432)
            and 170000 <= row[5] < 180000
            and row[6] == ROLE and row[7] == f"kitchenerp-disposable:regression:{name[-32:]}"
            and not row[8] and row[9] == 0 and not row[10], "CI_INITIALIZER_IDENTITY_REJECTED")
    # Check the exact cluster via its private administrator socket as well.
    require(admin("SHOW data_directory;") == str(cluster / "data"), "CI_WRONG_CLUSTER")
    require(connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()")) == 0,
            "CI_DATABASE_IN_USE")
    connection.rollback()


def verify_ready():
    name, _ = context()
    target = test_database_target("regression", os.environ)
    require(target.url.database == name, "CI_APPROVED_TARGET_MISMATCH")
    config = Config(str(BACKEND / "alembic.ini"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    engine = create_engine(target.url)
    try:
        def verify(connection):
            verify_connection(connection, target, f"kitchenerp-ci-preflight:{os.getpid()}")
        with guarded_connections(target.url, verify), engine.connect() as connection:
            validate_engine_target(target, connection.engine.url)
            require(170000 <= int(connection.scalar(text("SHOW server_version_num"))) < 180000, "CI_PG17_REQUIRED")
            require(connection.scalar(text("SELECT version_num FROM alembic_version")) == expected, "CI_SCHEMA_NOT_AT_HEAD")
            require(connection.scalar(text("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m')
                AND pg_get_userbyid(c.relowner)<>:owner"""), {"owner": ROLE}) == 0, "CI_OBJECT_OWNER_MISMATCH")
    finally:
        engine.dispose()


def prepare():
    name, cluster = context()
    require(not any(os.environ.get(key) for key in URL_KEYS), "CI_PREEXISTING_URL_REJECTED")
    require(admin("SHOW data_directory;") == str(cluster / "data"), "CI_WRONG_CLUSTER")
    require(admin("SELECT current_user;") == "postgres", "CI_ADMIN_IDENTITY_REJECTED")
    require(admin("SELECT current_setting('server_version_num')::int BETWEEN 170000 AND 179999;") == "t", "CI_PG17_REQUIRED")
    require(admin(f"SELECT count(*) FROM pg_roles WHERE rolname IN ('{ROLE}','{INITIALIZER}');") == "0", "CI_ROLE_ALREADY_EXISTS")
    require(admin(f"SELECT count(*) FROM pg_database WHERE datname='{name}';") == "0", "CI_DB_ALREADY_EXISTS")
    require(admin("SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;") == "0", "CI_HBA_INVALID")
    password, init_password = secrets.token_hex(32), secrets.token_hex(32)
    mask(password)
    mask(init_password)
    target_url = URL.create("postgresql+psycopg", username=ROLE, password=password,
                            host="127.0.0.1", port=5432, database=name)
    init_url = target_url.set(username=INITIALIZER, password=init_password)
    mask(target_url.render_as_string(hide_password=False))
    mask(init_url.render_as_string(hide_password=False))
    # Names are regex-validated and passwords are generated hexadecimal strings.
    flags = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
    admin(f"CREATE ROLE {ROLE} NOLOGIN {flags} PASSWORD '{password}';\n"
          f"CREATE ROLE {INITIALIZER} LOGIN {flags} PASSWORD '{init_password}';\n"
          f"CREATE DATABASE {name} OWNER {ROLE} TEMPLATE template0 ENCODING 'UTF8';\n"
          f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
          f"GRANT CONNECT ON DATABASE {name} TO {INITIALIZER};\n"
          f"COMMENT ON DATABASE {name} IS 'kitchenerp-disposable:regression:{name[-32:]}';")
    admin(f"REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE,CREATE ON SCHEMA public TO {INITIALIZER};", name)
    configure_urls(init_url)
    engine = create_engine(init_url)
    try:
        with guarded_connections(init_url, lambda conn: verify_initializer(conn, name, cluster)):
            with engine.connect() as connection:
                require(connection.scalar(text("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'""")) == 0,
                        "CI_DATABASE_NOT_EMPTY")
                require(connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%'")) == 0,
                        "CI_UNEXPECTED_SCHEMA")
            # env.py reads these process-only settings. No direct unguarded CLI.
            from app.core.config import settings
            require(make_url(settings.database_url) == init_url and make_url(settings.test_database_url) == init_url,
                    "CI_CACHED_SETTINGS_MISMATCH")
            config = Config(str(BACKEND / "alembic.ini"))
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    # Only the newly approved DB is affected; the initializer owns nothing elsewhere.
    admin(f"REASSIGN OWNED BY {INITIALIZER} TO {ROLE};\n"
          f"REVOKE ALL ON SCHEMA public FROM {INITIALIZER};", name)
    admin(f"REVOKE CONNECT ON DATABASE {name} FROM {INITIALIZER};\n"
          f"ALTER ROLE {INITIALIZER} NOLOGIN;\nALTER ROLE {ROLE} LOGIN;")
    require(admin(f"SELECT NOT rolcanlogin FROM pg_roles WHERE rolname='{INITIALIZER}';") == "t",
            "CI_INITIALIZER_STILL_ENABLED")
    raw = configure_urls(target_url)
    verify_ready()
    # Persist test credentials only in the ephemeral job environment, not artifacts.
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
        for key in URL_KEYS:
            output.write(f"{key}={raw}\n")
    print("Approved empty DB initialized to head; restricted owner verified; initializer login disabled.")


def report_counts(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return len(cases) - failed - skipped, failed, skipped


def run_batch(batch):
    verify_ready()
    report = Path(os.environ["RUNNER_TEMP"]) / f"kitchenerp-{batch}.xml"
    result = subprocess.run([sys.executable, "-B", "-m", "pytest", *BATCHES[batch],
        "--database-tests", "-m", "not migration", "--ignore-glob=*_migration.py",
        "-q", "--tb=short", "-x", "-p", "no:cacheprovider",
        f"--basetemp={Path(os.environ['RUNNER_TEMP']) / ('pytest-' + batch)}", f"--junitxml={report}"])
    passed, failed, skipped = report_counts(report)
    summary = f"{batch}: {passed} passed, {failed} failed/error, {skipped} skipped (batches overlap)."
    print(summary)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
        output.write(summary + "\n\n")
    require(result.returncode == 0 and failed == 0 and skipped == 0 and passed > 0, "CI_TEST_BATCH_NOT_PASSED")
    require(batch not in {"h01", "h07"} or passed == {"h01": 4, "h07": 5}[batch], "CI_TARGET_CASE_COUNT_CHANGED")
    verify_ready()


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in {"prepare", *BATCHES}, "CI_MODE_REQUIRED")
        prepare() if sys.argv[1] == "prepare" else run_batch(sys.argv[1])
    except Exception as error:
        # Do not leak driver errors, SQL parameters or credential-bearing URLs.
        if isinstance(error, RuntimeError) and re.fullmatch(r"CI_[A-Z_]+", str(error)):
            print(str(error), file=sys.stderr)
        print("CI_DATABASE_OR_TEST_STAGE_FAILED; stopped without retry or fallback.", file=sys.stderr)
        sys.exit(1)
