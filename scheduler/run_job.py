"""
scheduler/run_job.py — daily collection entry point.

Usage:
    python3 scheduler/run_job.py

Exit codes:
    0  at least one source succeeded
    1  every source failed (cron/systemd can alert on this)

Logs to stdout and to logs/collection.log (appended).
DATABASE_URL env var overrides default DSN (dbname=exchange_rates).
"""
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from scheduler.runner import run_all
from scheduler.health import quick_health_check
from scheduler.control import CollectionControl

# ── logging ───────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "collection.log"),
    ],
)
log = logging.getLogger("run_job")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
    started = datetime.now(timezone.utc).isoformat()
    log.info("collection started at=%s dsn=%s", started, dsn.split("@")[-1])

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:
        log.error("db connect failed: %s", exc)
        sys.exit(1)

    try:
        # Check if collection is paused
        control = CollectionControl(conn)
        if control.is_paused():
            pause_info = control.get_pause_info()
            log.warning("collection paused by=%s reason=%s", 
                       pause_info.get('paused_by'), 
                       pause_info.get('reason'))
            return
        
        # Run health check
        if not quick_health_check(conn):
            log.error("health check failed - aborting collection")
            sys.exit(1)
        
        log.info("health check passed - starting collection")
        
        results = run_all(conn)
    finally:
        conn.close()

    total = len(results)
    succeeded = sum(1 for r in results if r.get("status") in ("success", "partial_success"))
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = total - succeeded - failed

    for r in results:
        log.info(
            "source=%s status=%s accepted=%s flagged=%s rejected=%s dupes=%s",
            r.get("source_id"), r.get("status"),
            r.get("accepted", "-"), r.get("flagged", "-"),
            r.get("rejected", "-"), r.get("duplicates", "-"),
        )

    log.info(
        "collection finished: total=%d succeeded=%d failed=%d skipped=%d",
        total, succeeded, failed, skipped,
    )

    # Exit 1 only if every source failed (partial success is still success)
    if succeeded == 0 and total > 0:
        log.error("all sources failed — check alerts")
        sys.exit(1)


if __name__ == "__main__":
    main()
