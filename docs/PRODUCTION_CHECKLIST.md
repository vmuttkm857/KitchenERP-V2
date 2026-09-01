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
- [ ] `MEDIA_ROOT=/var/lib/kitchenerp/media` (or another persistent private path) exists, is writable only by the backend service account, and is included in file backups.
- [ ] `REFRESH_COOKIE_SECURE=true` and `REFRESH_COOKIE_SAMESITE=lax`.
- [ ] `CORS_ORIGINS` contains only the exact HTTPS frontend origin, never `*` or localhost.
- [ ] `VITE_API_BASE_URL=/api/v1`; no provider URL or secret is compiled into the frontend.
- [ ] Environment files are readable only by the service account.

## Database and bootstrap

- [ ] A new PostgreSQL database and least-privilege application role exist.
- [ ] `alembic upgrade head` completed as an explicit deployment step.
- [ ] `alembic current` equals `20260901_0012 (head)`.
- [ ] Initial admin was created interactively with `python -m app.cli.create_admin`.
- [ ] 每位操作人員都有獨立帳號；至少兩位 active admin，避免唯一管理員保護造成營運阻塞。
- [ ] Users/Audit API 對一般 user 回傳 403；所有 hard-delete 僅 admin 可執行。
- [ ] `audit_logs` 可寫入並只能由 admin 查詢；沒有任何 Audit PATCH/DELETE endpoint。
- [ ] No V1 test data was imported.
- [ ] Connection budget fits PostgreSQL: 2 workers × (5 pool + 5 overflow) = 20 maximum app connections.

## Runtime verification

- [ ] Backend runs under systemd without `--reload` and binds only `127.0.0.1:8000`.
- [ ] Uvicorn trusts forwarded headers only from `127.0.0.1`.
- [ ] Audit IP 目前使用直接 peer IP；啟用代理來源 IP 前，已明確設定並驗證 Caddy trusted-proxy 邊界，不信任任意 `X-Forwarded-For`。
- [ ] `GET /api/v1/health` returns 200 and the expected version.
- [ ] `GET /api/v1/ready` returns 200 with database/schema checks `ok`.
- [ ] Login, master-data creation, recipe, menu, calculations, snapshot, purchase and export smoke tests pass.
- [ ] 401/403/409/422/500 show safe messages; logs contain no credentials or tokens.

## Backup and operations

- [ ] Daily `pg_dump -Fc` job runs outside the web/static directory.
- [ ] `MEDIA_ROOT` is backed up separately; the media archive and PostgreSQL dump share a timestamp/backup-set identifier because `pg_dump` does not contain image files.
- [ ] Retention is daily 7, weekly 4 and monthly 3; at least one copy is off-host.
- [ ] Backup storage has access control and encryption at rest.
- [ ] Restore rehearsal completed into a separate empty database and was recorded.
- [ ] Restore rehearsal uses a matching DB/media pair, restores media ownership/permissions, and verifies both present and deliberately missing-image behavior.
- [ ] Upgrade and rollback owner, maintenance window and user communication are agreed.
- [ ] Monitoring alerts on service failure, readiness failure, disk pressure and backup failure.
