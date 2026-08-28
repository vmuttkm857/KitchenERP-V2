# KitchenERP V2 Production Checklist

## Host and network

- [ ] Linux host has 1–2 vCPU, 2–4 GB RAM, 20 GB+ SSD and monitored free space.
- [ ] Public firewall exposes only TCP 80/443; SSH is restricted; PostgreSQL is not public.
- [ ] DNS points the approved hostname to the host.
- [ ] Caddy obtains a valid HTTPS certificate and HTTP redirects to HTTPS.
- [ ] Caddy security headers and 10 MB request limit are active.

## Configuration and secrets

- [ ] `APP_ENV=production`, `LOG_LEVEL=INFO`, `DB_ECHO=false`.
- [ ] `APP_VERSION` identifies the deployed release or commit SHA.
- [ ] `DATABASE_URL`, `JWT_SECRET`, and `CORS_ORIGINS` are injected outside Git.
- [ ] `REFRESH_COOKIE_SECURE=true` and `REFRESH_COOKIE_SAMESITE=lax`.
- [ ] `CORS_ORIGINS` contains only the exact HTTPS frontend origin, never `*` or localhost.
- [ ] `VITE_API_BASE_URL=/api/v1`; no provider URL or secret is compiled into the frontend.
- [ ] Environment files are readable only by the service account.

## Database and bootstrap

- [ ] A new PostgreSQL database and least-privilege application role exist.
- [ ] `alembic upgrade head` completed as an explicit deployment step.
- [ ] `alembic current` equals `20260828_0006 (head)`.
- [ ] Initial admin was created interactively with `python -m app.cli.create_admin`.
- [ ] No V1 test data was imported.
- [ ] Connection budget fits PostgreSQL: 2 workers × (5 pool + 5 overflow) = 20 maximum app connections.

## Runtime verification

- [ ] Backend runs under systemd without `--reload` and binds only `127.0.0.1:8000`.
- [ ] Uvicorn trusts forwarded headers only from `127.0.0.1`.
- [ ] `GET /api/v1/health` returns 200 and the expected version.
- [ ] `GET /api/v1/ready` returns 200 with database/schema checks `ok`.
- [ ] Login, master-data creation, recipe, menu, calculations, snapshot, purchase and export smoke tests pass.
- [ ] 401/403/409/422/500 show safe messages; logs contain no credentials or tokens.

## Backup and operations

- [ ] Daily `pg_dump -Fc` job runs outside the web/static directory.
- [ ] Retention is daily 7, weekly 4 and monthly 3; at least one copy is off-host.
- [ ] Backup storage has access control and encryption at rest.
- [ ] Restore rehearsal completed into a separate empty database and was recorded.
- [ ] Upgrade and rollback owner, maintenance window and user communication are agreed.
- [ ] Monitoring alerts on service failure, readiness failure, disk pressure and backup failure.

