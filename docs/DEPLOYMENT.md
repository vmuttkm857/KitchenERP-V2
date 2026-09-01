# KitchenERP V2 Deployment Guide

This guide prepares a small production installation for 3–5 concurrent users. The primary recommendation is one modest Linux host running Caddy, React static files and the FastAPI service, plus PostgreSQL on the same private host or a small managed PostgreSQL instance. Kubernetes, Redis, queues and microservices are intentionally absent.

## 1. Architecture

```text
Browser
  → HTTPS Caddy (one public hostname)
      ├─ /       → frontend/dist static React files
      └─ /api/*  → 127.0.0.1:8000 FastAPI
                         → private PostgreSQL
```

Same-origin routing keeps cookies and CORS simple. PostgreSQL and port 8000 must not be publicly reachable. Caddy is preferred because it handles certificate issuance and renewal automatically; Nginx remains a viable operator-selected alternative but is not maintained here as a second configuration.

## 2. Minimum resources

- 1 vCPU and 2 GB RAM is a reasonable initial minimum; 2 vCPU and 4 GB gives safer headroom for builds, PostgreSQL and PDF/Excel generation.
- Start with 20 GB SSD, monitor growth, and keep backup capacity separate.
- A small PostgreSQL service is sufficient. Keep normal provider connection reservations in mind.
- Two Uvicorn workers support this workload. With defaults, `2 × (pool_size 5 + overflow 5) = 20` possible application connections. Add migration/administration connections and keep the total below PostgreSQL `max_connections`. One worker reduces the budget to 10 when the DB limit is small.

Docker is optional, not required. A Python virtual environment + systemd + Caddy is simpler for this system and keeps PostgreSQL backup tooling visible to the operator.

## 3. Host prerequisites

Install Python 3.12, PostgreSQL client tools (`psql`, `pg_dump`, `pg_restore`), Node/pnpm for release builds, Caddy, and Git or a release-artifact transfer tool. Create an unprivileged `kitchenerp` OS account and directories under `/opt/kitchenerp`, `/etc/kitchenerp`, `/var/log/kitchenerp`, and a protected backup mount.

Firewall rules should expose only 80/443 publicly. Restrict SSH by source or VPN. PostgreSQL should listen only on a private interface or localhost and accept only the application role.

## 4. Production environment

Store `/etc/kitchenerp/backend.env` outside the repository with mode `600`, owned by the service account. Production secrets must come from this environment file or the hosting secret store—not `.env`, frontend variables, command arguments or Git.

```dotenv
APP_ENV=production
APP_VERSION=<release-or-short-commit-sha>
DATABASE_URL=postgresql+psycopg://<app-user>:<secret>@<private-db-host>:5432/kitchenerp_v2
JWT_SECRET=<unique-random-value-at-least-32-characters>
CORS_ORIGINS=["https://erp.example.invalid"]
REFRESH_COOKIE_SECURE=true
REFRESH_COOKIE_SAMESITE=lax
REFRESH_COOKIE_NAME=kitchenerp_refresh
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=7
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT_SECONDS=30
DB_POOL_RECYCLE_SECONDS=1800
DB_ECHO=false
LOG_LEVEL=INFO
MEDIA_ROOT=/var/lib/kitchenerp/media
```

Replace every placeholder. `MEDIA_ROOT` must be a persistent directory writable by the backend service account; it stores authenticated dish photos and must not be the frontend/Caddy public root. Production startup fails if the database, JWT secret, explicit production origin or media path is absent, if cookies are not Secure, if localhost/wildcard CORS is used, or if SQL echo is enabled. `SameSite=None` is unnecessary for the recommended same-origin design and would still require Secure.

## 5. Fresh database and first administrator

Create an empty `kitchenerp_v2` database owned by a dedicated application role. Do not load V1: its records are test data only.

From `backend/`, with the production environment loaded:

```text
python -m venv .venv
.venv/bin/pip install .
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/python -m app.cli.create_admin --username <admin-name> --display-name "<display name>"
```

The CLI prompts twice without echo, has no default password, safely rejects duplicates, and commits through the existing User Service. Do not place the password on the command line. After login, users create production master data through the UI.

## 6. Frontend build

The same-origin default is `/api/v1`. Do not put secrets in Vite variables: every `VITE_*` value is public in the browser bundle.

```text
cd frontend
pnpm install --frozen-lockfile
VITE_API_BASE_URL=/api/v1 pnpm run build
```

Copy `frontend/dist` to the path configured as `FRONTEND_ROOT`. Do not serve source maps unless the operational need is accepted.

## 7. Backend and reverse proxy

Install `deployment/systemd/kitchenerp-backend.service.example`, adjust paths, then enable the service. Production never uses `--reload`. The example binds to localhost, uses two workers and trusts forwarded headers only from the local Caddy proxy.

Install `deployment/Caddyfile.example`; set `ERP_DOMAIN` and `FRONTEND_ROOT` in Caddy's service environment. Validate with `caddy validate`, then reload. Caddy provides HTTPS, SPA fallback, API proxying, compression, a 10 MB request limit and conservative security headers. The limit applies to requests, not export responses. HSTS is production HTTPS-only.

For a Windows production-like rehearsal, use a dedicated PowerShell session without reload:

```text
backend\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

For Windows Server production, wrap the same command in a managed service such as NSSM and restrict proxy headers to the known local proxy. Linux/systemd remains the maintained recommendation.

## 8. Health, readiness and logging

- `/api/v1/health` proves the process is alive and returns only service/version metadata.
- `/api/v1/ready` performs `SELECT 1` and verifies the database Alembic revision equals the application head. It returns 503 when either check fails.
- Requests receive `X-Request-ID`. Logs include timestamp, level, method, path, status, duration and request ID.
- Unexpected exceptions are logged server-side; clients receive a generic message and request ID. Passwords, authorization headers, refresh tokens, DB URLs and request bodies are never logged.

Send stdout/stderr to the service journal or provider log collector with access control and retention. Production defaults to INFO, not DEBUG.

## 9. Backup and retention

Use PostgreSQL-native custom dumps. Schedule `scripts/backup_postgres.sh` daily with `DATABASE_URL` and `BACKUP_DIR` supplied by a protected service environment. It fails on `pg_dump` errors, creates mode-restricted files, and retains daily 7, weekly 4 and monthly 3 generations. Keep the directory outside the web root and Git repository.

At least one copy must be off-host. Treat backups as sensitive because they contain users, password hashes and business data; restrict access and use encrypted-at-rest storage. Alert on job failure and periodically verify the newest file exists and is non-empty.

`pg_dump` only backs up PostgreSQL records; it does **not** include files under `MEDIA_ROOT`. Back up the complete private media directory separately, for example as a permission-restricted `tar.gz` archive, and give the database dump and media archive the same timestamp or backup-set identifier. Keep both copies off-host under the same retention and encryption policy. For the closest DB/file recovery point, briefly stop application writes while producing the paired database and media backups; copying live media is acceptable only with the documented possibility that a file uploaded or replaced during the two operations may not match the dump.

Restore a paired backup with the backend stopped: restore PostgreSQL into the controlled target, restore the matching media archive to the configured `MEDIA_ROOT`, restore ownership and restrictive permissions, then start the backend and verify representative dish photos and recipe-card PDFs. Restoring only the DB can leave referenced images missing; restoring only media can leave orphan files that are not referenced by any profile. Missing files are treated as “no available photo” in profile/plan reads and PDF generation continues without the image. Orphan files are not publicly reachable and do not break exports, but consume disk space; review them against database image filenames before any manual cleanup rather than deleting files by age alone.

## 10. Restore rehearsal

Never overwrite development or production during rehearsal.

1. Create a separate empty database such as `kitchenerp_restore_rehearsal` with a temporary role/credentials.
2. Export `PGHOST`, `PGPORT`, `PGUSER` and `PGPASSWORD`, then run `scripts/restore_postgres.sh --target-db kitchenerp_restore_rehearsal --dump <file>`. Credentials remain outside process arguments.
3. Point a temporary backend process at the restored URL.
4. Run `alembic current`; confirm it equals the application head.
5. Compare selected row counts and verify foreign keys with normal reads.
6. Restore the matching media archive into an isolated rehearsal media path and point the temporary backend `MEDIA_ROOT` to it.
7. Check `/health`, `/ready`, login, representative dish photos and one recipe-card export.
8. Destroy only the explicitly named rehearsal database and media directory after recording the result.

The restore script refuses the configured `PRODUCTION_DATABASE_NAME` unless `--allow-production` is explicit. A real production restore additionally requires an approved incident plan, outage, verified backup and named operator.

## 11. Release upgrade

1. Announce a short maintenance window and stop writes.
2. Produce and verify a pre-deploy database backup.
3. Stage the exact release artifact; record `APP_VERSION`.
4. Install locked backend dependencies and build the frontend.
5. Review migration notes, then run `alembic upgrade head` once as a separate deployment command.
6. Only after migration succeeds, restart the backend and publish the frontend build.
7. Validate Caddy, `/health`, `/ready`, login and the manual smoke checklist.
8. Reopen access and monitor logs/readiness.

The application never runs migrations automatically, preventing multiple workers from racing on schema changes.

## 12. Rollback

For application-only defects with a compatible schema, restore the previous backend release and static build, restart, and smoke test. Do not assume `alembic downgrade` is safe. For destructive or incompatible database changes, stop writes and restore the verified pre-deploy dump into a controlled database according to the incident plan, then run the compatible application release. Record every rollback decision.

## 13. Troubleshooting

- Startup validation error: check required environment variable names without printing their values.
- `/health` 200 but `/ready` 503: verify PostgreSQL reachability, credentials and `alembic current`; do not route traffic until ready.
- Login cookie missing: confirm browser uses HTTPS, `Secure=true`, same hostname and `/api/v1/auth` path.
- CORS failure: same-origin should not need cross-origin access; otherwise use the exact HTTPS origin, never `*`.
- Too many DB connections: calculate workers × (pool + overflow), reduce workers/overflow, and inspect leaked or long transactions.
- Export failure: use the request ID to find the server exception; never show raw errors to users.

Complete `docs/PRODUCTION_CHECKLIST.md` before choosing or provisioning a provider.
