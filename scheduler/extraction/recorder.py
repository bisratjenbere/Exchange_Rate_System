"""
Recorder module - Database writes and transaction management.

Extracted from scheduler/runner.py lines 184-301 and helper functions 390-559.
Handles:
- Raw capture storage
- Run status calculation
- Failure counter management
- Alert creation
- Fallback attempt and expiration
- All transaction boundaries

This module owns ALL transaction logic from run_source().
No other extraction module should call conn.commit() or conn.rollback().

PRESERVED BUGS:
- Bug #1: Double status in stale path (finish_run twice)
- Bug #2: Dry-run orphaned runs (start_run commits before dry_run check)
- Bug #3: Silent raw capture failure (bare except: pass)
- Bug #4: Invisible fallback expiration (no return value)
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pipeline.ingest import ingest
from pipeline.runs import finish_run, record_raw_capture
from infrastructure.rate_source_repository import RateSourceRepository


ALERT_AFTER_CONSECUTIVE_FAILURES = 2


@dataclass(frozen=True)
class IngestMetrics:
    """Metrics from pipeline.ingest() execution."""
    accepted: int
    flagged: int
    rejected: int
    duplicates: int
    candidates: int
    suspicious: bool


@dataclass(frozen=True)
class RecordingResult:
    """Result of recording collection outcome to database."""
    status: str  # "success", "partial_success", "failed", "dry_run"
    accepted: int
    flagged: int
    rejected: int
    duplicates: int
    candidates: int
    schema_changed: bool
    duration_ms: int
    # For failed paths
    error_code: Optional[str] = None
    error_summary: Optional[str] = None


def _store_raw_capture(conn, run_id: int, reason: str, raw_content: str) -> None:
    """
    Store raw HTML/JSON content for debugging.
    
    BUG #3: Caller wraps in bare except: pass, causing silent failures.
    
    Extracted from: Lines 390-397
    """
    import hashlib
    from pipeline.runs import record_raw_capture as pipeline_record_raw_capture
    
    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()
    pipeline_record_raw_capture(conn, run_id, reason, content_hash)


def _run_status(ingest_result) -> str:
    """
    Calculate run status from ingest result.
    
    Extracted from: Lines 398-402
    """
    if ingest_result.rejected > 0 and ingest_result.accepted == 0:
        return "failed"
    if ingest_result.rejected > 0 or ingest_result.errors:
        return "partial_success"
    return "success"


def _reset_failure_counter(conn, source_id: int) -> None:
    """
    Reset consecutive failure counter on success.
    
    Extracted from: Lines 403-416
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_source
               SET consecutive_failures = 0, last_failure_code = NULL
               WHERE id = %s""",
            (source_id,),
        )


def _increment_failure_counter(conn, source_id: int, error_code: str) -> bool:
    """
    Increment consecutive failure counter.
    
    Returns True if alert threshold reached and 24h since last alert.
    
    Extracted from: Lines 417-435
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_source
               SET consecutive_failures = consecutive_failures + 1,
                   last_failure_at = now(),
                   last_failure_code = %s
               WHERE id = %s
               RETURNING consecutive_failures, alert_sent_at""",
            (error_code, source_id),
        )
        row = cur.fetchone()
        if not row:
            return False
        consecutive, alert_sent_at = row
        if consecutive >= ALERT_AFTER_CONSECUTIVE_FAILURES:
            if alert_sent_at is None or (
                datetime.now(timezone.utc) - alert_sent_at
            ).total_seconds() > 86400:
                return True
    return False


def _write_alert(conn, source_id: int, error_code: str, error_summary: str) -> None:
    """
    Write alert record.
    
    Extracted from: Lines 436-449
    """
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO source_alert (source_id, error_code, summary, created_at)
               VALUES (%s, %s, %s, now())""",
            (source_id, error_code, (error_summary or "")[:500]),
        )
        cur.execute(
            "UPDATE rate_source SET alert_sent_at = now() WHERE id = %s",
            (source_id,),
        )


def _try_af_fallback(conn, source_id: int, adapter_key: str, user_agent: str):
    """
    Attempt Addis Fortune fallback for specific sources.
    
    Returns collection result dict on success, None on failure.
    Commits internally on success (transaction boundary).
    
    Extracted from: Lines 450-525
    """
    import psycopg2.errors
    from adapters.addis_fortune.adapter import get_adapter_for_key
    from pipeline.runs import start_run
    
    af_adapter = get_adapter_for_key(adapter_key)
    if af_adapter is None:
        return None

    try:
        run_id = start_run(conn, source_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None

    t0 = time.monotonic()
    try:
        raw_content, http_status = af_adapter.fetch_raw(
            af_adapter.get_source_url(), user_agent, ssl_verify=True
        )
        result_obj = af_adapter.parse(raw_content)
        if isinstance(result_obj, tuple):
            records, _ = result_obj
        else:
            records = result_obj.records if hasattr(result_obj, 'records') else result_obj

        fetched_at = datetime.now(timezone.utc)
        ingest_result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=True)

        duration_ms = int((time.monotonic() - t0) * 1000)
        run_status = _run_status(ingest_result)
        finish_run(
            conn, run_id, run_status,
            http_status=http_status,
            records_found=len(records),
            records_accepted=ingest_result.accepted,
            records_flagged=ingest_result.flagged,
            records_duplicated=ingest_result.duplicates,
            duration_ms=duration_ms,
            is_fallback=True,
            fallback_adapter="addis_fortune",
        )
        if run_status in ("success", "partial_success"):
            repo = RateSourceRepository(conn)
            repo.update_last_success(source_id)
            _reset_failure_counter(conn, source_id)
        conn.commit()
        return {
            "source_id": source_id,
            "status": run_status,
            "accepted": ingest_result.accepted,
            "flagged": ingest_result.flagged,
            "rejected": ingest_result.rejected,
            "duplicates": ingest_result.duplicates,
            "fallback": "addis_fortune",
        }
    except Exception as exc:
        from infrastructure.error_classifier import default_classifier
        
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_classifier = default_classifier
        error_code, error_summary = error_classifier.classify(exc)
        try:
            finish_run(conn, run_id, "failed",
                       error_code=error_code,
                       error_summary=error_summary[:500] if error_summary else None,
                       duration_ms=duration_ms,
                       is_fallback=True,
                       fallback_adapter="addis_fortune")
            conn.commit()
        except Exception:
            conn.rollback()
        return None


def _expire_stale_fallback_current(conn, source_id: int) -> None:
    """
    Expire stale fallback observations on primary success.
    
    BUG #4: Side effect with no return value - invisible to caller.
    
    Extracted from: Lines 526-559
    """
    from db.repositories.rate_observation_repository import RateObservationRepository
    
    # Note: Using hardcoded value from runner.py constant
    FALLBACK_TTL_DAYS = 3
    
    repo = RateObservationRepository(conn)
    repo.expire_stale_fallback_current(source_id, FALLBACK_TTL_DAYS)


def record_normal_success(
    conn,
    run_id: int,
    source_id: int,
    records: list,
    raw_content: str,
    http_status: int,
    adapter,
    schema_changed: bool,
    t0: float,
    circuit_breaker,
    adapter_key: str,
) -> RecordingResult:
    """
    Record a normal successful collection.
    
    Handles:
    - Schema fingerprint update
    - Ingest execution
    - Suspicious data raw capture
    - Run finish
    - Success bookkeeping (last_success, failure counter, circuit breaker, fallback expiration)
    - Transaction commit
    
    Extracted from: Lines 184-253
    Transaction: Commits at line 251
    """
    repo = RateSourceRepository(conn)
    
    # Update schema fingerprint if changed
    if schema_changed:
        new_fp = adapter.schema_fingerprint(raw_content)
        repo.update_schema_fingerprint(source_id, new_fp)
    
    # Ingest records
    fetched_at = datetime.now(timezone.utc)
    result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)
    
    # Store suspicious data
    if result.suspicious:
        _store_raw_capture(conn, run_id, "suspicious_data", raw_content)
    
    duration_ms = int((time.monotonic() - t0) * 1000)
    run_status = _run_status(result)
    
    # Finish run
    finish_run(
        conn, run_id, run_status,
        http_status=http_status,
        records_found=len(records),
        records_accepted=result.accepted,
        records_flagged=result.flagged,
        records_duplicated=result.duplicates,
        duration_ms=duration_ms,
        is_fallback=False,
    )
    
    # Success bookkeeping
    if run_status in ("success", "partial_success"):
        repo.update_last_success(source_id)
        _reset_failure_counter(conn, source_id)
        circuit_breaker.record_success(adapter_key)
        _expire_stale_fallback_current(conn, source_id)  # BUG #4: Side effect
    
    conn.commit()
    
    return RecordingResult(
        status=run_status,
        accepted=result.accepted,
        flagged=result.flagged,
        rejected=result.rejected,
        duplicates=result.duplicates,
        candidates=result.candidates,
        schema_changed=schema_changed,
        duration_ms=duration_ms,
    )


def record_dry_run(
    conn,
    run_id: int,
    records: list,
    raw_content: str,
    schema_changed: bool,
    t0: float,
) -> dict:
    """
    Handle dry-run mode - ingest then rollback.
    
    BUG #2: start_run() already committed, so this rollback creates orphaned run.
    
    Extracted from: Lines 194-220
    Transaction: Rollback at line 206 (but start_run committed at line 102)
    """
    # Note: ingest has already been called before this function
    # We just need to calculate metrics and rollback
    
    # This is a simplified dry-run - in actual code, ingest is called in runner
    # For Phase 4, we're just handling the rollback logic
    
    duration_ms = int((time.monotonic() - t0) * 1000)
    
    conn.rollback()  # BUG #2: start_run already committed
    
    return {
        "source_id": None,  # Caller will fill this in
        "status": "dry_run",
        "records_found": len(records),
        "schema_changed": schema_changed,
        "duration_ms": duration_ms,
        # Note: would_accept/would_reject/would_flag/would_duplicate
        # are calculated from ingest result, which caller has
    }


def record_failed_with_fallback_attempt(
    conn,
    run_id: int,
    source_id: int,
    error_code: str,
    error_summary: str,
    http_status: Optional[int],
    records_count: int,
    t0: float,
    adapter_key: str,
    user_agent: str,
) -> dict:
    """
    Record a failed collection and attempt fallback.
    
    Handles zero/stale decision path.
    
    Extracted from: Lines 121-177
    Transaction: Commits at line 139
    """
    duration_ms = int((time.monotonic() - t0) * 1000)
    
    finish_run(
        conn, run_id, "failed",
        http_status=http_status,
        records_found=records_count,
        records_accepted=0,
        records_flagged=0,
        records_duplicated=0,
        error_code=error_code,
        error_summary=error_summary,
        duration_ms=duration_ms,
        is_fallback=False,
    )
    
    needs_alert = _increment_failure_counter(conn, source_id, error_code)
    if needs_alert:
        _write_alert(conn, source_id, error_code, error_summary)
    
    conn.commit()
    
    # Try fallback
    af_res = _try_af_fallback(conn, source_id, adapter_key, user_agent)
    if af_res is not None:
        return af_res
    
    return {
        "source_id": source_id,
        "status": "failed",
        "error_code": error_code,
        "detail": error_summary,
    }


def record_stale_retained(
    conn,
    run_id: int,
    source_id: int,
    records: list,
    raw_content: str,
    http_status: int,
    t0: float,
) -> dict:
    """
    Record stale records that are retained as standing rate.
    
    BUG #1: Calls finish_run('failed') in record_failed_with_fallback_attempt,
    then calls finish_run('success') here - double status update.
    
    Extracted from: Lines 144-171
    Transaction: Commits at line 165
    """
    fetched_at = datetime.now(timezone.utc)
    result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)
    
    duration_ms = int((time.monotonic() - t0) * 1000)
    
    # BUG #1: This is the second finish_run call for this run_id
    finish_run(
        conn, run_id, "success",
        http_status=http_status,
        records_found=len(records),
        records_accepted=result.accepted,
        records_flagged=result.flagged,
        records_duplicated=result.duplicates,
        error_code="stale_feed",
        error_summary="Primary returned stale records; retained as standing rate",
        duration_ms=duration_ms,
        is_fallback=False,
    )
    
    repo = RateSourceRepository(conn)
    repo.update_last_success(source_id)
    _reset_failure_counter(conn, source_id)
    
    conn.commit()
    
    return {
        "source_id": source_id,
        "status": "success",
        "accepted": result.accepted,
        "flagged": result.flagged,
        "rejected": result.rejected,
        "duplicates": result.duplicates,
    }


def record_exception(
    conn,
    run_id: int,
    source_id: int,
    error_code: str,
    error_summary: str,
    raw_content: Optional[str],
    http_status: Optional[int],
    t0: float,
    circuit_breaker,
    adapter_key: str,
    user_agent: str,
) -> dict:
    """
    Record an exception during collection.
    
    BUG #3: Silent raw capture failure (bare except: pass).
    
    Extracted from: Lines 254-299
    Transaction: Commits at line 287 (or rollback at 289 if finish_run fails)
    """
    duration_ms = int((time.monotonic() - t0) * 1000)
    
    circuit_breaker.record_failure(adapter_key)
    
    # BUG #3: Try to store raw (silent failure)
    if raw_content and error_code in ("parse_failure", "schema_change"):
        try:
            _store_raw_capture(conn, run_id, error_code, raw_content)
        except Exception:
            pass  # <-- SILENT FAILURE
    
    # Try to finish run + alert
    try:
        finish_run(
            conn, run_id, "failed",
            http_status=http_status,
            records_found=0,
            records_accepted=0,
            records_flagged=0,
            records_duplicated=0,
            error_code=error_code,
            error_summary=error_summary,
            duration_ms=duration_ms,
            is_fallback=False,
        )
        
        needs_alert = _increment_failure_counter(conn, source_id, error_code)
        if needs_alert:
            _write_alert(conn, source_id, error_code, error_summary)
        
        conn.commit()
    except Exception:
        conn.rollback()  # If finish_run itself fails
    
    # Last-ditch fallback attempt (commits internally)
    af_result = _try_af_fallback(conn, source_id, adapter_key, user_agent)
    if af_result:
        return af_result
    
    return {
        "source_id": source_id,
        "status": "failed",
        "error_code": error_code,
        "detail": error_summary,
    }
