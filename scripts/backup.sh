#!/usr/bin/env bash
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f .env.local ]; then
    set -a
    source .env.local
    set +a
elif [ -f .env ]; then
    set -a
    source .env
    set +a
fi

TARGET_URL="${DATABASE_URL_UNPOOLED:-$DATABASE_URL}"
if [ -z "$TARGET_URL" ]; then
    echo "DATABASE_URL is not set" >&2
    exit 1
fi

TARGET_URL="${TARGET_URL/-pooler/}"

mkdir -p backups
TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILE="backups/exchange_rates_${TIMESTAMP}.sql.gz"
LATEST_FILE="backups/exchange_rates_backup_latest.sql.gz"

if pg_dump "$TARGET_URL" | gzip > "$BACKUP_FILE"; then
    FILE_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || echo 0)
    if [ "$FILE_SIZE" -gt 10000 ]; then
        cp "$BACKUP_FILE" "$LATEST_FILE"
        echo "Backup complete ($FILE_SIZE bytes): $BACKUP_FILE"
        echo "Updated latest: $LATEST_FILE"
    else
        echo "Backup output too small ($FILE_SIZE bytes), possible error. Keeping existing latest." >&2
        rm -f "$BACKUP_FILE"
        exit 1
    fi
else
    echo "pg_dump failed. Keeping existing latest backup." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi
