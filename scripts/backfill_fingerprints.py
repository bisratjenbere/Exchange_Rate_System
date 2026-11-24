"""
scripts/backfill_fingerprints.py

Recomputes snapshot_fingerprint and fingerprint_version for all rows that are
not already on FINGERPRINT_VERSION 3.

Decision D-1 Option A: backfill before deploying new fingerprint code.
A backup table fingerprint_backup_v2 is created first for deterministic rollback.

Usage:
    python3 -m scripts.backfill_fingerprints [--dry-run] [--batch-size N]
"""
import argparse
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg2

from pipeline.fingerprint import compute_fingerprint, FINGERPRINT_VERSION
from domain.records import AdapterRecord


def _get_conn():
    import os
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DB_DSN", "dbname=exchange_rates")
    return psycopg2.connect(dsn)


def _ensure_backup_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fingerprint_backup_v2 (
                observation_id      BIGINT PRIMARY KEY,
                old_fingerprint     CHAR(64),
                old_version         SMALLINT,
                backed_up_at        TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
    conn.commit()


def _backup_batch(conn, ids):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO fingerprint_backup_v2 (observation_id, old_fingerprint, old_version)
            SELECT id, snapshot_fingerprint, fingerprint_version
            FROM rate_observation
            WHERE id = ANY(%s)
            ON CONFLICT (observation_id) DO NOTHING
        """, (ids,))


def _fetch_batch(conn, batch_size, offset):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                id,
                source_id,
                source_currency_code,
                category_id,
                buying_rate,
                selling_rate,
                effective_date,
                effective_date_basis,
                source_publication_key,
                quote_currency_code,
                unit_multiplier,
                fetched_at
            FROM rate_observation
            WHERE fingerprint_version < %s OR fingerprint_version IS NULL
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (FINGERPRINT_VERSION, batch_size, offset))
        return cur.fetchall()


def _update_batch(conn, updates):
    with conn.cursor() as cur:
        cur.executemany("""
            UPDATE rate_observation
            SET snapshot_fingerprint = %s,
                fingerprint_version  = %s
            WHERE id = %s
        """, updates)


def _row_to_record(row):
    (obs_id, source_id, source_currency_code, category_id,
     buying_rate, selling_rate, effective_date, effective_date_basis,
     source_publication_key, quote_currency_code, unit_multiplier, fetched_at) = row

    record = AdapterRecord(
        source_currency_code=source_currency_code or "",
        category="cash",  # category_id not needed for fingerprint
        buying_rate=Decimal(str(buying_rate)) if buying_rate is not None else None,
        selling_rate=Decimal(str(selling_rate)) if selling_rate is not None else None,
        effective_date=effective_date,
        effective_date_basis=effective_date_basis or "unknown",
        source_publication_key=source_publication_key,
        quote_currency_code=quote_currency_code,
        unit_multiplier=int(unit_multiplier) if unit_multiplier is not None else 1,
    )
    collection_date = effective_date or (
        fetched_at.date() if fetched_at else date.today()
    )
    return obs_id, source_id, record, collection_date


def run(dry_run=False, batch_size=500):
    conn = _get_conn()
    _ensure_backup_table(conn)

    offset = 0
    total_updated = 0

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting backfill to fingerprint v{FINGERPRINT_VERSION} (dry_run={dry_run})")

    while True:
        rows = _fetch_batch(conn, batch_size, offset)
        if not rows:
            break

        ids = [r[0] for r in rows]
        _backup_batch(conn, ids)

        updates = []
        for row in rows:
            obs_id, source_id, record, collection_date = _row_to_record(row)
            fp = compute_fingerprint(record, source_id, collection_date=collection_date)
            updates.append((fp, FINGERPRINT_VERSION, obs_id))

        if not dry_run:
            _update_batch(conn, updates)
            conn.commit()

        total_updated += len(updates)
        print(f"  processed {total_updated} rows (offset={offset})")
        offset += batch_size

    print(f"[{datetime.now(timezone.utc).isoformat()}] Done. Total rows processed: {total_updated}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    run(dry_run=args.dry_run, batch_size=args.batch_size)
