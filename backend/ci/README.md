# Manual PostgreSQL regression CI

This CI is **not yet verified on a GitHub runner**. It does not deploy anything.
Existing `tests/DATABASE_SAFETY.md`, `database_safety.py`, and `conftest.py` remain
unchanged. No Windows database, production connection or real business data is
used. No GitHub repository/environment Secrets are needed.

## Approval and first execution

1. Review and separately authorize committing/pushing the CI files and the local
   H01/H06/H04/H07 history. This preparation does not authorize either operation.
2. The workflow must be present on the default branch before manual dispatch is
   available. Review Actions permissions and the account's minutes/spending limits.
3. Approve an exact new disposable DB name and the `kitchenerp_regression_test`
   role. Supply that name as `approved_database_name` when manually dispatching;
   the required format is `kitchenerp_regression_test_<32 lowercase hex>`.
   The dispatch authorizes creating that DB, migrating its **empty** schema to
   head, and writing/cleaning synthetic test data only inside it.
4. Run the workflow manually against the approved commit. There are no push,
   pull-request, schedule or deployment triggers.

## Isolation and privileges

- Ubuntu 24.04, Python 3.12, explicitly verified PostgreSQL **17** binaries.
  Missing binaries are installed from the official HTTPS PGDG apt source using
  its fingerprint-checked signing key and apt Signed-By verification.
- A fresh private cluster lives under `/tmp/kitchenerp-ci-<run>-<attempt>`.
  An existing directory or TCP listener on port 5432 causes failure; nothing is
  stopped, reused or deleted to make room. The VM lifecycle removes resources.
- PostgreSQL listens only on `127.0.0.1:5432`. A private Unix socket is used only
  by the provisioning administrator, never by Alembic or the API tests.
- HBA allows the two exact CI roles over IPv4 loopback only to the approved DB,
  using SCRAM; other TCP connections are rejected. PUBLIC has no DB or schema
  privileges. The owner is `kitchenerp_regression_test`; the comment is exactly
  `kitchenerp-disposable:regression:<the same 32 hex suffix>`.
- Both roles have no superuser, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS or
  inherited memberships. Provisioning uses the cluster's OS `postgres` account.
  The separate `kitchenerp_ci_initializer` login receives only CONNECT and
  USAGE/CREATE on this DB's public schema, and runs Alembic as a non-admin.
- Before migration, verify the actual TCP endpoint, role/session identity,
  PostgreSQL major version, DB owner/marker, absence of competing sessions,
  exact new cluster identity and empty user schema. Every SQLAlchemy connection
  opened by Alembic is checked, with no URL/connection override or fallback.
  This is an explicit CI provisioning step outside pytest; it does not enable
  migrations in regression pytest or change `guarded_migration()`.
- After upgrade, only this new DB's initializer-owned objects are reassigned to
  the regression owner. Initializer privileges are revoked and LOGIN disabled.
  The test role's LOGIN is then enabled. Existing `verify_connection()` verifies
  its real identity/privileges/marker/ownership; Alembic head and object ownership
  are checked again before and after every test batch.
- Passwords are random, masked (including full URLs), passed through process/job
  environment only and never saved in `.env`, repository files or artifacts.
  No DB dumps, SQL logs or JUnit reports are uploaded. Bootstrap failures print
  fixed safety codes instead of credential-bearing driver exceptions.

## Test batches and failure behavior

Four sequential, separate pytest processes run H01 (4 cases), H07 (5 cases), the
Snapshots/Ordering Adjustments/Exports/Purchases APIs, then full API + Integration
+ Regression. Batches overlap and their counts must not be added together.
All use `--database-tests -m "not migration" --ignore-glob=*_migration.py -q
--tb=short -x -p no:cacheprovider`, with no xdist or third-party plugin autoload.
Migration upgrade/downgrade **tests** require another dedicated database and
are deliberately not part of this workflow.

The existing fixtures close sessions and delete synthetic rows between cases.
Test or teardown failure, nonzero exit, empty collection, skipped/xfail cases,
or H01/H07 count mismatches fail the batch and stop subsequent steps. There is
no retry, schema rebuild or fallback DB. XML reports and pytest temp files stay
in RUNNER_TEMP; the summary separates passed/failed/skipped counts.

First execution must confirm package availability, initializer permissions for
all current migrations, actual TCP identity, fixture cleanup and real PostgreSQL
transaction/locking behavior. Offline checks cannot establish those facts.

## Local offline checks (no database)

From `backend`, using the existing Python environment:
`python -B -m unittest discover -s ci -p test_postgresql_regression.py`

The entry points reject non-GitHub-hosted/non-manual environments. Do **not** run
the bootstrap/prepare commands on a workstation or production server. There is
no local PostgreSQL setup or Windows Docker requirement.
