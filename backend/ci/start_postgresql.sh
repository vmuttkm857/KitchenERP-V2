#!/usr/bin/env bash
# Only creates a NEW cluster on an ephemeral GitHub-hosted runner.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]]
[[ "${GITHUB_EVENT_NAME:-}" == workflow_dispatch && "${RUNNER_OS:-}" == Linux ]]
[[ "${CI_APPROVED_DATABASE:-}" =~ ^kitchenerp_regression_test_[0-9a-f]{32}$ ]]
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]]
# Never stop or reuse another listener/cluster, even on a disposable runner.
[[ -z "$(ss -H -ltn 'sport = :5432')" ]]
pgbin=/usr/lib/postgresql/17/bin
if [[ ! -x "$pgbin/postgres" ]]; then
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg postgresql-common
  key="$RUNNER_TEMP/kitchenerp-pgdg.asc"
  curl --fail --silent --show-error --location --proto '=https' \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc -o "$key"
  fingerprint=$(gpg --batch --show-keys --with-colons "$key" | awk -F: '$1=="fpr" {print $10; exit}')
  [[ "$fingerprint" == B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8 ]]
  sudo install -m 644 "$key" /usr/share/postgresql-common/pgdg-kitchenerp.asc
  printf '%s\n' \
    'deb [signed-by=/usr/share/postgresql-common/pgdg-kitchenerp.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main' \
    | sudo tee /etc/apt/sources.list.d/kitchenerp-pgdg.list >/dev/null
  # Avoid package installation automatically creating a second cluster.
  printf 'create_main_cluster = false\n' | sudo tee /etc/postgresql-common/createcluster.conf >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17
fi
"$pgbin/postgres" --version | grep -E '^postgres \(PostgreSQL\) 17\.'
[[ -z "$(ss -H -ltn 'sport = :5432')" ]]
cluster="/tmp/kitchenerp-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
[[ ! -e "$cluster" ]]
sudo install -d -m 700 -o postgres -g postgres "$cluster" "$cluster/socket"
sudo -u postgres "$pgbin/initdb" -D "$cluster/data" --no-locale --encoding=UTF8 \
  --auth-local=peer --auth-host=scram-sha-256 >/dev/null
{
  printf 'local all postgres peer\n'
  printf 'host %s kitchenerp_ci_initializer 127.0.0.1/32 scram-sha-256\n' "$CI_APPROVED_DATABASE"
  printf 'host %s kitchenerp_regression_test 127.0.0.1/32 scram-sha-256\n' "$CI_APPROVED_DATABASE"
  printf 'host all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n'
} | sudo -u postgres tee "$cluster/data/pg_hba.conf" >/dev/null
sudo -u postgres "$pgbin/pg_ctl" -D "$cluster/data" -l "$cluster/server.log" \
  -o "-h 127.0.0.1 -p 5432 -k $cluster/socket -c password_encryption=scram-sha-256 -c log_statement=none -c log_min_error_statement=panic" \
  -w start >/dev/null
printf 'CI_PG_CLUSTER=%s\n' "$cluster" >> "$GITHUB_ENV"
echo 'Fresh PostgreSQL 17 cluster started; no pre-existing cluster reused.'
