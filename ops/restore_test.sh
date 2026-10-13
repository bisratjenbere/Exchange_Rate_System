#!/usr/bin/env bash
# ops/restore_test.sh — verify the latest backup restores cleanly.
#
# Creates a temporary DB, restores into it, checks row counts match
# production, then drops the temp DB.
#
# Usage:
#   ./ops/restore_test.sh

set -euo pipefail

BACKUP_DIR="$(dirname "$0")/../backups"
LATEST="$(ls -t "$BACKUP_DIR"/exchange_rates_*.sql.gz 2>/dev/null | head -1)"

if [[ -z "$LATEST" ]]; then
    echo "ERROR: no backup found in $BACKUP_DIR" >&2
    exit 1
fi

TMPDB="exchange_rates_restore_test_$$"
echo "$(date -u +%FT%TZ) testing restore of $LATEST into $TMPDB"

createdb "$TMPDB"
trap "dropdb '$TMPDB'" EXIT

gunzip -c "$LATEST" | psql -q "$TMPDB"

# Compare row counts between production and restored DB
for TABLE in bank rate_source rate_observation collection_run; do
    PROD=$(psql -tAq exchange_rates -c "SELECT COUNT(*) FROM $TABLE")
    REST=$(psql -tAq "$TMPDB"       -c "SELECT COUNT(*) FROM $TABLE")
    if [[ "$PROD" != "$REST" ]]; then
        echo "FAIL: $TABLE prod=$PROD restored=$REST" >&2
        exit 1
    fi
    echo "  OK $TABLE: $PROD rows"
done

echo "$(date -u +%FT%TZ) restore test passed"
