from typing import Optional
from db.repositories.collection_run_repository import CollectionRunRepository

STUCK_RUN_THRESHOLD_HOURS = 4
STUCK_RUN_THRESHOLD_MINUTES = 5


def start_run(conn, source_id: int) -> int:
    repo = CollectionRunRepository(conn)
    run_id = repo.start_run(source_id)
    conn.commit()
    return run_id


def finish_run(
    conn,
    run_id: int,
    status: str,
    http_status: Optional[int] = None,
    records_found: int = 0,
    records_accepted: int = 0,
    records_flagged: int = 0,
    error_code: Optional[str] = None,
    error_summary: Optional[str] = None,
    duration_ms: Optional[int] = None,
    records_duplicated: int = 0,
    is_fallback: bool = False,
    fallback_adapter: Optional[str] = None,
):
    repo = CollectionRunRepository(conn)
    repo.finish_run(
        run_id,
        status,
        http_status,
        records_found,
        records_accepted,
        records_flagged,
        error_code,
        error_summary,
        duration_ms,
        records_duplicated,
        is_fallback,
        fallback_adapter,
    )
    conn.commit()


def reap_stuck_runs(conn, threshold_minutes: int = 5) -> int:
    repo = CollectionRunRepository(conn)
    count = repo.reap_stuck_runs(threshold_minutes)
    conn.commit()
    return count


def recover_stuck_run(conn, source_id: int) -> Optional[int]:
    repo = CollectionRunRepository(conn)
    stuck_id = repo.recover_stuck_run(source_id, STUCK_RUN_THRESHOLD_MINUTES)
    conn.commit()
    return stuck_id


def record_raw_capture(
    conn,
    run_id: int,
    capture_reason: str,
    content_hash: str,
    storage_reference: Optional[str] = None,
    retention_days: int = 90,
):
    repo = CollectionRunRepository(conn)
    repo.insert_raw_capture(run_id, capture_reason, content_hash, storage_reference, retention_days)
    conn.commit()


def get_running_run(conn, source_id: int) -> Optional[int]:
    repo = CollectionRunRepository(conn)
    return repo.get_running_run(source_id)
