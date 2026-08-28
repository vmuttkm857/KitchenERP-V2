#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 --target-db DATABASE_NAME --dump FILE [--allow-production]" >&2
    echo "Connection credentials must be supplied through PGHOST/PGPORT/PGUSER/PGPASSWORD." >&2
    exit 2
}

target_db=""
dump_file=""
allow_production="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-db) target_db="${2:-}"; shift 2 ;;
        --dump) dump_file="${2:-}"; shift 2 ;;
        --allow-production) allow_production="true"; shift ;;
        *) usage ;;
    esac
done

[[ -n "${target_db}" && -n "${dump_file}" ]] || usage
[[ -f "${dump_file}" ]] || { echo "Dump file does not exist." >&2; exit 2; }
if [[ -n "${PRODUCTION_DATABASE_NAME:-}" && "${target_db}" == "${PRODUCTION_DATABASE_NAME}" && "${allow_production}" != "true" ]]; then
    echo "Refusing to restore to the configured production database without --allow-production." >&2
    exit 3
fi

pg_restore --exit-on-error --no-owner --no-privileges --dbname="${target_db}" "${dump_file}"
echo "Restore completed. Run readiness and smoke verification before using this database."
