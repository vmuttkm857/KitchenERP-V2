"""Offline CI policy tests; all connection/subprocess boundaries are mocked."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import postgresql_regression as ci


NAME = "kitchenerp_regression_test_0123456789abcdef0123456789abcdef"


class ContextTests(unittest.TestCase):
    def environment(self):
        return dict(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted",
                    GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1",
                    CI_PG_CLUSTER=str(Path("/tmp/kitchenerp-ci-123-1")), CI_APPROVED_DATABASE=NAME, APP_ENV="test")

    def check(self, change=None, dotenv=False):
        env = self.environment()
        env.update(change or {})
        with patch.dict(os.environ, env, clear=True), patch.object(ci.sys, "platform", "linux"), \
                patch.object(ci.Path, "cwd", return_value=ci.BACKEND), patch.object(ci.Path, "exists", return_value=dotenv):
            return ci.context()

    def test_valid_hosted_manual_context(self):
        self.assertEqual(self.check(), (NAME, Path("/tmp/kitchenerp-ci-123-1")))

    def test_other_hosts_events_and_wrong_database_names_fail_closed(self):
        for change in ({"RUNNER_ENVIRONMENT": "self-hosted"}, {"GITHUB_EVENT_NAME": "push"},
                       {"CI_APPROVED_DATABASE": "kitchenerp_prod"}, {"CI_APPROVED_DATABASE": "kitchenerp_test"},
                       {"CI_APPROVED_DATABASE": NAME + "';"}, {"APP_ENV": "production"},
                       {"CI_PG_CLUSTER": "/tmp/other"}, {"GITHUB_RUN_ID": "../other"}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.check(change)

    def test_inherited_connection_overrides_are_rejected(self):
        for key in ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE",
                    "PGSERVICEFILE", "PGOPTIONS", "PGPASSWORD", "PGPASSFILE", "MIGRATION_TEST_DATABASE_URL",
                    "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_XDIST_WORKER"):
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "OVERRIDE"):
                self.check({key: "unexpected"})

    def test_dotenv_is_not_a_ci_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "DOTENV"):
            self.check(dotenv=True)


class InitializerTests(unittest.TestCase):
    def identity(self):
        return [NAME, ci.INITIALIZER, ci.INITIALIZER, "127.0.0.1", 5432, 170000,
                ci.ROLE, "kitchenerp-disposable:regression:" + NAME[-32:], False, 0, False]

    def verify(self, row=None, others=0, data_directory=None):
        connection = Mock()
        connection.execute.return_value.one.return_value = row or self.identity()
        connection.scalar.return_value = others
        with patch.object(ci, "admin", return_value=data_directory or str(Path("/cluster/data"))):
            ci.verify_initializer(connection, NAME, Path("/cluster"))
        return connection

    def test_initializer_checks_identity_and_closes_read_transaction(self):
        self.verify().rollback.assert_called_once()

    def test_wrong_role_endpoint_owner_marker_or_privilege_is_rejected(self):
        for index, value in ((0, "kitchenerp_test"), (1, "postgres"), (2, "postgres"),
                             (3, "172.18.0.2"), (4, 5433), (5, 160000), (5, 180000),
                             (6, "postgres"), (7, "kitchenerp-disposable:regression"),
                             (8, True), (9, 1), (10, True)):
            row = self.identity()
            row[index] = value
            with self.subTest(index=index, value=value), self.assertRaisesRegex(RuntimeError, "IDENTITY"):
                self.verify(row)

    def test_wrong_cluster_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "CLUSTER"):
            self.verify(data_directory="/existing/postgresql/data")

    def test_other_application_sessions_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "IN_USE"):
            self.verify(others=1)

    def test_existing_url_stops_before_any_admin_operation(self):
        with patch.object(ci, "context", return_value=(NAME, Path("/cluster"))), \
                patch.dict(os.environ, {"DATABASE_URL": "unexpected"}, clear=True), patch.object(ci, "admin") as admin:
            with self.assertRaisesRegex(RuntimeError, "PREEXISTING"):
                ci.prepare()
            admin.assert_not_called()


class ConnectionTests(unittest.TestCase):
    def url(self):
        return ci.URL.create("postgresql+psycopg", username=ci.INITIALIZER,
                             host="127.0.0.1", port=5432, database=NAME)

    def test_ddl_connection_is_verified_and_original_connect_restored(self):
        url = self.url()
        connection, verify = Mock(), Mock()
        engine = SimpleNamespace(url=url)
        with patch.dict(os.environ, {key: url.render_as_string() for key in ci.URL_KEYS}, clear=True), \
                patch.object(ci.Engine, "connect", return_value=connection) as original:
            with ci.guarded_connections(url, verify):
                self.assertIs(ci.Engine.connect(engine), connection)
            self.assertIs(ci.Engine.connect, original)
            verify.assert_called_once_with(connection)

    def test_target_or_environment_mismatch_never_opens_connection(self):
        url = self.url()
        for change_engine in (True, False):
            engine = SimpleNamespace(url=url.set(database="kitchenerp_prod") if change_engine else url)
            env = {key: url.render_as_string() for key in ci.URL_KEYS}
            if not change_engine:
                env["DATABASE_URL"] = url.set(database="kitchenerp_test").render_as_string()
            with patch.dict(os.environ, env, clear=True), patch.object(ci.Engine, "connect") as original:
                with ci.guarded_connections(url, Mock()), self.assertRaises(RuntimeError):
                    ci.Engine.connect(engine)
                original.assert_not_called()

    def test_identity_failure_closes_connection_before_ddl(self):
        url, connection = self.url(), Mock()
        with patch.dict(os.environ, {key: url.render_as_string() for key in ci.URL_KEYS}, clear=True), \
                patch.object(ci.Engine, "connect", return_value=connection):
            with ci.guarded_connections(url, Mock(side_effect=RuntimeError("CI_REJECTED"))), self.assertRaises(RuntimeError):
                ci.Engine.connect(SimpleNamespace(url=url))
        connection.close.assert_called_once()


class ReportTests(unittest.TestCase):
    def test_report_keeps_skips_and_errors_out_of_passed_count(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.xml"
            report.write_text('<testsuites><testsuite><testcase/><testcase><skipped/></testcase>'
                              '<testcase><error/></testcase><testcase><failure/></testcase></testsuite></testsuites>')
            self.assertEqual(ci.report_counts(report), (1, 2, 1))

    def test_skip_empty_error_or_changed_target_counts_stop_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            for counts, returncode in (((4, 0, 1), 0), ((0, 0, 0), 0), ((3, 1, 0), 1), ((3, 0, 0), 0)):
                summary = Path(folder) / "summary"
                with self.subTest(counts=counts), patch.object(ci, "verify_ready"), \
                        patch.object(ci.subprocess, "run", return_value=SimpleNamespace(returncode=returncode)), \
                        patch.object(ci, "report_counts", return_value=counts), \
                        patch("builtins.print"), \
                        patch.dict(os.environ, {"RUNNER_TEMP": folder, "GITHUB_STEP_SUMMARY": str(summary)}, clear=True):
                    with self.assertRaises(RuntimeError):
                        ci.run_batch("h01")

    def test_successful_target_checks_database_before_and_after_subprocess(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(ci, "verify_ready") as verify, \
                    patch.object(ci.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run, \
                    patch.object(ci, "report_counts", return_value=(4, 0, 0)), patch("builtins.print"), \
                    patch.dict(os.environ, {"RUNNER_TEMP": folder, "GITHUB_STEP_SUMMARY": str(Path(folder) / 'summary')}, clear=True):
                ci.run_batch("h01")
                self.assertEqual(verify.call_count, 2)
                args = run.call_args.args[0]
                self.assertIn("--database-tests", args)
                self.assertIn("--ignore-glob=*_migration.py", args)
                self.assertNotIn("--migration-tests", args)


if __name__ == "__main__":
    unittest.main()
