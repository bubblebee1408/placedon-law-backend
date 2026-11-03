#!/usr/bin/env bash
# The live-database regressions: what the offline gate cannot prove, against a real
# PostgreSQL 16 with FORCE ROW LEVEL SECURITY applied by the repository's migrations.
# Run by .github/workflows/gate.yml and by `make test-db`. Each script creates and drops its
# own placedon_throwaway_* database, so it never touches the database you develop against.
#
# Needs: PLACEDON_PGHOST, PLACEDON_PG_ADMIN (a superuser), PLACEDON_PG_APP (placedon_app,
# NOSUPERUSER NOBYPASSRLS), and PGPASSWORD for both.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
host="${PLACEDON_PGHOST:-localhost}"

# A provisioning failure prints SKIP and exits 0 locally, by design. Here that would be a
# green check over nothing, so SKIP or a missing "N/M passed" line fails.
for s in scripts/vault_upload_atomic_integration.py \
         scripts/vault_failed_retry_integration.py \
         scripts/vault_ingest_authz_integration.py \
         scripts/conversation_persist_integration.py \
         scripts/review_table_list_integration.py \
         scripts/company_profile_integration.py \
         scripts/login_email_integration.py \
         scripts/spend_ledger_integration.py; do
  echo "::group::$s --run"
  out=$(python "$s" --run 2>&1) || { echo "$out"; exit 1; }
  echo "$out"
  echo "::endgroup::"
  if grep -q '^SKIP' <<<"$out" || ! grep -qE '[0-9]+/[0-9]+ passed' <<<"$out"; then
    echo "::error::$s did not run against the database"; exit 1
  fi
done

# Row-level security proof: migrations applied as the superuser; every visibility assertion
# runs as placedon_app. --run refuses any database not named placedon_throwaway_*.
db=placedon_throwaway_rls
psql -h "$host" -U postgres -v ON_ERROR_STOP=1 -q -c "DROP DATABASE IF EXISTS $db WITH (FORCE)" \
     -c "CREATE DATABASE $db"
out=$(PLACEDON_ADMIN_DATABASE_URL="postgresql://$host/$db?user=postgres" \
      PLACEDON_DATABASE_URL="postgresql://$host/$db?user=placedon_app" \
      python scripts/rls_integration.py --run 2>&1) || { echo "$out"; exit 1; }
echo "$out"
if grep -q '^  REFUSED:' <<<"$out" || ! grep -qE '^[0-9]+/[0-9]+ passed' <<<"$out"; then
  echo "::error::rls_integration.py did not run against the database"; exit 1
fi
psql -h "$host" -U postgres -q -c "DROP DATABASE $db WITH (FORCE)"
echo "db regressions: all passed"
