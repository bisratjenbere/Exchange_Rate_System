from datetime import datetime, timezone, timedelta
from typing import Optional
import psycopg2

STUCK_RUN_THRESHOLD_HOURS = 4
STUCK_RUN_THRESHOLD_MINUTES = 5

def start_run(conn, source_id: int) -> int:
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
               duration_ms: Optional[int] = None,
               records_duplicated: int = 0,
               is_fallback: bool = False,
               fallback_adapter: Optional[str] = None):
    if status not in ("success", "partial_success", "failed"):
        raise ValueError(f"Invalid finish status: {status!r}")
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collection_run SET
                   finished_at        = now(),
                   status             = %s,
                   http_status        = %s,
                   records_found      = %s,
                   records_accepted   = %s,
                   records_flagged    = %s,
                   records_duplicated = %s,
                   is_fallback        = %s,
                   fallback_adapter   = %s,
                   error_code         = %s,
                   error_summary      = %s,
                   duration_ms        = %s
               WHERE id = %s""",
            (status, http_status, records_found, records_accepted, records_flagged,
             records_duplicated, is_fallback, fallback_adapter,
             error_code, error_summary, duration_ms, run_id),
        )
    conn.commit()

def reap_stuck_runs(conn, threshold_minutes: int = 5) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collection_run SET
                   finished_at   = now(),
                   status        = 'failed',
                   error_code    = 'timeout_reaped',
                   error_summary = 'Run stuck in running state exceeded threshold'
               WHERE status = 'running' AND started_at < %s
               RETURNING id""",
            (threshold,),
        )
        reaped = cur.fetchall()
    conn.commit()
    return len(reaped)

def recover_stuck_run(conn, source_id: int) -> Optional[int]:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_RUN_THRESHOLD_MINUTES)
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
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM collection_run WHERE source_id=%s AND status='running' LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
