from datetime import datetime, timezone, timedelta

from db.repositories.collection_run_repository import CollectionRunRepository
from infrastructure.rate_source_repository import RateSourceRepository

STALE_HOURS_DEFAULT = 26


def check_failed_runs(conn, since_hours: int = 24) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    rows = CollectionRunRepository(conn).get_failed_runs_since(cutoff)
    return [
        {
            "type": "failed_run",
            "source_id": r[1],
            "detail": f"run {r[0]} failed at {r[2].isoformat()} — {r[3]}: {r[4]}",
        }
        for r in rows
    ]


def check_schema_changes(conn, since_hours: int = 24) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    rows = CollectionRunRepository(conn).get_schema_changes_since(cutoff)
    return [
        {
            "type": "schema_change",
            "source_id": r[1],
            "detail": f"schema change captured at {r[2].isoformat()} (hash {r[3][:12]}…)",
        }
        for r in rows
    ]


def check_disappearing_data(conn) -> list:
    rows = CollectionRunRepository(conn).get_last_successful_run_per_source()
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
    cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
    rows = RateSourceRepository(conn).get_stale_sources(cutoff)
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
    alerts = []
    alerts.extend(check_failed_runs(conn, since_hours=since_hours))
    alerts.extend(check_schema_changes(conn, since_hours=since_hours))
    alerts.extend(check_disappearing_data(conn))
    alerts.extend(check_stale_rates(conn, stale_hours=stale_hours))
    return alerts
