#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -z "$DATABASE_URL" ]; then
    if [ -f .env.local ]; then
        set -a
        source .env.local
        set +a
    elif [ -f .env ]; then
        set -a
        source .env
        set +a
    fi
fi

if [ -z "$DATABASE_URL" ]; then
    echo "DATABASE_URL is not set" >&2
    exit 1
fi

mkdir -p backups
TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILE="backups/exchange_rates_${TIMESTAMP}.sql.gz"
LATEST_FILE="backups/exchange_rates_backup_latest.sql.gz"

pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
cp "$BACKUP_FILE" "$LATEST_FILE"

echo "Backup complete: $BACKUP_FILE"
echo "Updated latest: $LATEST_FILE"
