"""
alerts/checker.py — alert conditions for the exchange rate system.

Four alert types (per execution-order.md Phase 7 step 26):
  1. failed_run        — a collection run finished with status='failed'
  2. schema_change     — a raw_capture row with reason='schema_change' in the last window
  3. disappearing_data — an enabled source returned 0 records_found on its last run
  4. stale_rates       — no successful run for an enabled source within staleness_hours

Each check returns a list of alert dicts:
  { "type": str, "source_id": int, "detail": str }

An empty list means no alerts for that check.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional


STALE_HOURS_DEFAULT = 26  # slightly over 24 h to allow for scheduling jitter


def check_failed_runs(conn, since_hours: int = 24) -> list:
    """Alert for any run that finished with status='failed' in the last since_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, source_id, finished_at, error_code, error_summary
               FROM collection_run
               WHERE status = 'failed' AND finished_at >= %s
               ORDER BY finished_at DESC""",
            (cutoff,),
        )
        rows = cur.fetchall()
    return [
        {
            "type": "failed_run",
            "source_id": r[1],
            "detail": f"run {r[0]} failed at {r[2].isoformat()} — {r[3]}: {r[4]}",
        }
        for r in rows
    ]


def check_schema_changes(conn, since_hours: int = 24) -> list:
    """Alert for any raw_capture with reason='schema_change' in the last since_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT rc.id, cr.source_id, rc.captured_at, rc.content_hash
               FROM raw_capture rc
               JOIN collection_run cr ON cr.id = rc.collection_run_id
               WHERE rc.capture_reason = 'schema_change' AND rc.captured_at >= %s
               ORDER BY rc.captured_at DESC""",
            (cutoff,),
        )
        rows = cur.fetchall()
    return [
        {
            "type": "schema_change",
            "source_id": r[1],
            "detail": f"schema change captured at {r[2].isoformat()} (hash {r[3][:12]}…)",
        }
        for r in rows
    ]


def check_disappearing_data(conn) -> list:
    """
    Alert when an enabled source's most recent finished run returned records_found=0.
    Gap review G: disappearing data triggers completeness warning.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (cr.source_id)
                   cr.source_id, cr.id, cr.finished_at, cr.records_found
               FROM collection_run cr
               JOIN rate_source rs ON rs.id = cr.source_id
               WHERE rs.is_enabled = TRUE
                 AND cr.status IN ('success', 'partial_success')
                 AND cr.finished_at IS NOT NULL
               ORDER BY cr.source_id, cr.finished_at DESC"""
        )
        rows = cur.fetchall()
    return [
        {
            "type": "disappearing_data",
            "source_id": r[0],
            "detail": f"last successful run {r[1]} at {r[2].isoformat()} returned 0 records",
        }
        for r in rows
        if r[3] == 0
    ]


def check_stale_rates(conn, stale_hours: int = STALE_HOURS_DEFAULT) -> list:
    """
    Alert when an enabled source has had no successful run within stale_hours.
    Covers sources that have never run (last_success_at IS NULL).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, adapter_key, last_success_at
               FROM rate_source
               WHERE is_enabled = TRUE
                 AND (last_success_at IS NULL OR last_success_at < %s)""",
            (cutoff,),
        )
        rows = cur.fetchall()
    return [
        {
            "type": "stale_rates",
            "source_id": r[0],
            "detail": (
                f"source '{r[1]}' last succeeded at {r[2].isoformat()}"
                if r[2]
                else f"source '{r[1]}' has never succeeded"
            ),
        }
        for r in rows
    ]


def run_all_checks(conn, since_hours: int = 24,
                   stale_hours: int = STALE_HOURS_DEFAULT) -> list:
    """Run all four checks and return combined alert list."""
    alerts = []
    alerts.extend(check_failed_runs(conn, since_hours=since_hours))
    alerts.extend(check_schema_changes(conn, since_hours=since_hours))
    alerts.extend(check_disappearing_data(conn))
    alerts.extend(check_stale_rates(conn, stale_hours=stale_hours))
    return alerts
