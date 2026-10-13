#!/usr/bin/env bash
# ops/backup.sh — dump the production exchange_rates database.
#
# Usage:
#   ./ops/backup.sh
#   DATABASE_URL=dbname=mydb ./ops/backup.sh
#
# Restore:
#   gunzip -c backups/exchange_rates_2026-10-12.sql.gz | psql exchange_rates
#
# Cron (daily at 04:00 UTC, before the 05:00 collection run):
#   0 4 * * * cd /home/bisru/Exchange_Rate_System && ./ops/backup.sh >> logs/backup.log 2>&1

set -euo pipefail

BACKUP_DIR="$(dirname "$0")/../backups"
mkdir -p "$BACKUP_DIR"

DB="${DATABASE_URL:-exchange_rates}"
DATE="$(date -u +%Y-%m-%d)"
OUT="$BACKUP_DIR/exchange_rates_${DATE}.sql.gz"

echo "$(date -u +%FT%TZ) backing up $DB → $OUT"
pg_dump "$DB" | gzip > "$OUT"
echo "$(date -u +%FT%TZ) done. size=$(du -h "$OUT" | cut -f1)"

# Keep last 30 days only
find "$BACKUP_DIR" -name "exchange_rates_*.sql.gz" -mtime +30 -delete
