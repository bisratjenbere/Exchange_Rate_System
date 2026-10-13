"""
pipeline/runs.py — collection run lifecycle.
LOCKED rules:
- One running run per source (enforced by DB partial unique index).
- A failed run never deletes or invalidates earlier observations.
- Stuck running rows recovered by a documented rule (not silent deletion).
- Raw capture triggered for: http_failure, parse_failure, schema_change, suspicious_data.
Gap review K: overlapping runs prevented; stale running row recovery documented.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import psycopg2

# A run is considered stuck if it has been running longer than this.
STUCK_RUN_THRESHOLD_HOURS = 4


def start_run(conn, source_id: int) -> int:
    """
    Start a new collection run. Returns run id.
    Raises psycopg2.errors.UniqueViolation if a run is already running for this source
    (enforced by uq_one_running_run_per_source partial unique index).
    """
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO collection_run (source_id, started_at, status)
               VALUES (%s, now(), 'running') RETURNING id""",
            (source_id,),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, status: str,
               http_status: Optional[int] = None,
               records_found: int = 0,
               records_accepted: int = 0,
               records_flagged: int = 0,
               error_code: Optional[str] = None,
               error_summary: Optional[str] = None,
               duration_ms: Optional[int] = None):
    """
    Mark a run finished with the given status.
    status must be one of: success, partial_success, failed.
    """
    if status not in ("success", "partial_success", "failed"):
        raise ValueError(f"Invalid finish status: {status!r}")
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collection_run SET
                   finished_at      = now(),
                   status           = %s,
                   http_status      = %s,
                   records_found    = %s,
                   records_accepted = %s,
                   records_flagged  = %s,
                   error_code       = %s,
                   error_summary    = %s,
                   duration_ms      = %s
               WHERE id = %s""",
            (status, http_status, records_found, records_accepted, records_flagged,
             error_code, error_summary, duration_ms, run_id),
        )
    conn.commit()


def recover_stuck_run(conn, source_id: int) -> Optional[int]:
    """
    If a run for source_id has been in 'running' status longer than
    STUCK_RUN_THRESHOLD_HOURS, mark it failed with error_code='stuck_run_recovered'.
    Returns the recovered run_id, or None if no stuck run found.
    Gap review K: documented recovery rule.
    """
    threshold = datetime.now(timezone.utc) - timedelta(hours=STUCK_RUN_THRESHOLD_HOURS)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM collection_run
               WHERE source_id = %s AND status = 'running' AND started_at < %s
               LIMIT 1""",
            (source_id, threshold),
        )
        row = cur.fetchone()
        if not row:
            return None
        stuck_id = row[0]
        cur.execute(
            """UPDATE collection_run SET
                   finished_at   = now(),
                   status        = 'failed',
                   error_code    = 'stuck_run_recovered',
                   error_summary = 'Run exceeded threshold and was recovered automatically'
               WHERE id = %s""",
            (stuck_id,),
        )
    conn.commit()
    return stuck_id


def record_raw_capture(conn, run_id: int, capture_reason: str,
                       content_hash: str, storage_reference: Optional[str] = None,
                       retention_days: int = 90):
    """
    Insert a raw_capture row.
    capture_reason: http_failure | parse_failure | schema_change | suspicious_data
    """
    valid_reasons = {"http_failure", "parse_failure", "schema_change", "suspicious_data"}
    if capture_reason not in valid_reasons:
        raise ValueError(f"Invalid capture_reason: {capture_reason!r}")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_capture
                   (collection_run_id, capture_reason, content_hash,
                    storage_reference, retention_until)
               VALUES (%s, %s, %s, %s, now()::date + %s)""",
            (run_id, capture_reason, content_hash, storage_reference, retention_days),
        )
    conn.commit()


def get_running_run(conn, source_id: int) -> Optional[int]:
    """Return the id of the currently running run for source_id, or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM collection_run WHERE source_id=%s AND status='running' LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
