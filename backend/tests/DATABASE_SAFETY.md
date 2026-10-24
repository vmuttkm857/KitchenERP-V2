# PostgreSQL test safety

Default `python -m pytest` runs database-free unit tests. PostgreSQL API,
integration, regression, and migration tests are skipped. Neither `.env` nor the
shared `kitchenerp_test` authorizes test writes. Unit tests cannot open SQLAlchemy
connections; Alembic upgrade and downgrade are denied by default.

## Dedicated databases (manual approval required)

This repository does **not** create, delete, rebuild, or provision test databases.
Before a database administrator provisions anything, obtain explicit approval
for the exact database and dedicated role. Never reuse an existing user database.

Provision two independent, disposable databases as needed:

| Purpose | Exact name pattern | Dedicated owner/login role |
| --- | --- | --- |
| Migration | `kitchenerp_migration_test_<32 lowercase hexadecimal characters>` | `kitchenerp_migration_test` |
| Regression | `kitchenerp_regression_test_<32 lowercase hexadecimal characters>` | `kitchenerp_regression_test` |

Both must be on `127.0.0.1:5432`. No URL options, alternate libpq connection
environment settings, inherited role memberships, superuser, CREATEDB,
CREATEROLE, replication, or BYPASSRLS are allowed. The database must be owned by
its dedicated role, with a database comment exactly
`kitchenerp-disposable:<migration|regression>:<the 32-character suffix>`.
The comment is an explicit disposable marker, not a secret or a substitute for
endpoint/role verification. Keep application servers and all user data out.

Provision the regression schema separately, with explicit approval, at Alembic
head before running tests. Regression tests never automatically migrate it.
Migration tests intentionally destroy/rebuild schema **inside their own database**
and must run separately from API/regression tests. Their existing teardown may
delete test rows; this is permitted only inside the verified disposable target.
After a failed migration test, stop and inspect that disposable database rather
than trying recovery against any other database. Database removal also needs
explicit approval and is not automated here.

## Explicit process configuration

Only after provisioning and approval, use process-scoped environment variables
(not `.env` edits). Set `APP_ENV=test` and set all three URLs to the exact same
approved destination:

- Migration: `MIGRATION_TEST_DATABASE_URL`, `DATABASE_URL`, `TEST_DATABASE_URL`;
  run `python -m pytest --migration-tests -m migration`.
- Regression: `REGRESSION_TEST_DATABASE_URL`, `DATABASE_URL`, `TEST_DATABASE_URL`;
  run `python -m pytest --database-tests -m "not migration"`.

Do not put passwords in shell history, shared logs, screenshots, or test reports.
Do not combine `--migration-tests` and `--database-tests`; separate processes
prevent cached application settings from targeting the wrong database.

Before every SQLAlchemy connection, the guard checks the exact configured URL.
It then reads PostgreSQL's actual database, server address/port, session/current
role, ownership, role privileges/memberships, disposable comment, and competing
application sessions. Mismatches close the connection before any test SQL.
Only this pytest process's tagged connections can coexist. Every upgrade and
downgrade also checks configuration consistency, cached application settings,
and rejects Config connection/URL overrides. No automatic database fallback.

No guard can make an administrator intentionally bypassing pytest safe. These
controls protect this test harness; direct external Alembic/psql commands remain
administrator responsibilities. Do not use xdist/multiple pytest workers against
one disposable database.
