#!/bin/sh
# Apply pending migrations to the local database the way production does them:
# backup first (as the superuser, who can read every row), apply as placedon_app
# (scripts/migrate.py refuses a superuser), then the elevated one-time bootstrap.
set -eu
ADMIN_URL="postgresql://postgres:${PGPASSWORD}@${PLACEDON_PGHOST}:5432/placedon"
python scripts/migrate.py --apply --url "$PLACEDON_DATABASE_URL" \
  --backup-dir /backups --backup-url "$ADMIN_URL"
psql "$ADMIN_URL" -q -v ON_ERROR_STOP=1 \
  -v tenant="$PLACEDON_GATEWAY_TENANT_ID" -v actor="$PLACEDON_GATEWAY_ACTOR_ID" \
  -f ops/dev/bootstrap.sql
echo "migrations applied; local tenant $PLACEDON_GATEWAY_TENANT_ID ready"
