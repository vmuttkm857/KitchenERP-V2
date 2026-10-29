# Explicit snapshot revisions: release and rollback contract

Migration `20261029_0028` follows `20261008_0027`. It adds only two nullable
header fields, their paired-value/standard-kind/hash check, an actor/intent unique
index, and atomically replaces the ordinary-content unique index. Historical
rows retain NULL intent fields. Criteria/revision uniqueness is unchanged.

Ordinary creation still queries **all** standard revisions by criteria/content,
including explicit revisions. Every writer takes the existing criteria advisory
transaction lock before deduplication and revision allocation. Explicit writers
first lock the actor/intent, then the criteria. Only authenticated requests on the
explicit endpoint may set intent fields, after H07 validates the current result.
Repeated successful intent + identical payload returns the prior commit; changing
its actor-scoped request hash is rejected. No current-source recalculation is
needed for a replay because it creates no new snapshot.

Intent-backed headers cannot be hard-deleted through the API: deletion would
erase retry history. This restriction does not change legacy ordinary deletion.
No purchase is automatically created, cancelled, moved or replaced. Existing
purchase uniqueness is per snapshot, not across revisions; operators must check
old purchases before ordering from a new revision.

## Implementation scope

The Revision feature changes/adds these 14 files. Pre-existing source-order and
session-diagnostic work is separate and is retained.

- `backend/app/api/v1/routes/snapshots.py`
- `backend/app/domains/snapshots/exceptions.py`
- `backend/app/domains/snapshots/models.py`
- `backend/app/domains/snapshots/repository.py`
- `backend/app/domains/snapshots/schemas.py`
- `backend/app/domains/snapshots/service.py`
- `backend/migrations/versions/20261029_0028_snapshot_revision_intents.py`
- `backend/tests/SNAPSHOT_REVISION_TESTING.md`
- `backend/tests/api/snapshots/test_snapshot_revisions_api.py`
- `backend/tests/integration/test_snapshot_revision_intents_migration.py`
- `backend/tests/unit/snapshots/test_revision_intents.py`
- `frontend/src/features/requirements/RequirementsPage.tsx`
- `frontend/src/features/requirements/snapshotRevisionIntent.ts`
- `frontend/tests/requirements-request-race.test.mjs`

## Safe validation

Follow `DATABASE_SAFETY.md` unchanged. Regression and Migration databases are
different approved disposable PostgreSQL databases. Never use shared test/dev or
production databases. Configure only process environment variables; no `.env`
changes. Regression schema must already be at head using separately authorized
safe initialization. No automatic schema initialization occurs in regression.

Regression command (dedicated regression target required):

```text
python -B -m pytest tests/api/snapshots/test_snapshot_revisions_api.py --database-tests -q --tb=short -x -p no:cacheprovider
```

Migration command (separate dedicated migration target required):

```text
python -B -m pytest tests/integration/test_snapshot_revision_intents_migration.py --migration-tests -m migration -q --tb=short -x -p no:cacheprovider
```

Tests cover real PostgreSQL constraint/transaction/concurrent service calls,
ordinary-vs-explicit dedup, replay, rollback, legacy rows and purchase links.
Offline service and SQL-generation tests do not certify PostgreSQL concurrency.
Do not disable the existing connection guard if parallel tests are refused.

## Downgrade and application rollback

Downgrade takes an exclusive table lock, then refuses if **any** persisted intent
exists. It neither deletes versions nor erases idempotency history to force old
uniqueness to pass. With no intents it restores the old unique index and removes
the nullable fields. Run this only on an authorized target; no production DDL is
authorized by local development approval.

After explicit revisions exist, retain the new schema during application rollback
and review old-code compatibility, especially old hard-delete paths. Do not run
an old application that can delete intent headers without a separate mitigation.
Never restore a database backup over newly written business data automatically.
