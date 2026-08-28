#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"
: "${BACKUP_DIR:?BACKUP_DIR must be set to a protected off-web directory}"

timestamp="$(date -u +%Y%m%d_%H%M)"
daily_dir="${BACKUP_DIR}/daily"
weekly_dir="${BACKUP_DIR}/weekly"
monthly_dir="${BACKUP_DIR}/monthly"
filename="kitchenerp_${timestamp}.dump"

mkdir -p "${daily_dir}" "${weekly_dir}" "${monthly_dir}"
umask 077
export PGDATABASE="${DATABASE_URL}"
pg_dump --format=custom --file="${daily_dir}/${filename}"
unset PGDATABASE

day_of_week="$(date -u +%u)"
day_of_month="$(date -u +%d)"
if [[ "${day_of_week}" == "7" ]]; then
    cp "${daily_dir}/${filename}" "${weekly_dir}/${filename}"
fi
if [[ "${day_of_month}" == "01" ]]; then
    cp "${daily_dir}/${filename}" "${monthly_dir}/${filename}"
fi

find "${daily_dir}" -type f -name 'kitchenerp_*.dump' -mtime +6 -delete
find "${weekly_dir}" -type f -name 'kitchenerp_*.dump' -mtime +27 -delete
find "${monthly_dir}" -type f -name 'kitchenerp_*.dump' -mtime +92 -delete

printf 'Backup completed: %s\n' "${daily_dir}/${filename}"
