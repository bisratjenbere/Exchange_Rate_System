import hashlib
import logging
import psycopg2.errors
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from db.repositories.rate_observation_repository import RateObservationRepository
from db.repositories.collection_run_repository import CollectionRunRepository
from domain.fallback import FallbackPolicy
from infrastructure.rate_source_repository import RateSourceRepository
from pipeline.ingest import ingest
from pipeline.runs import finish_run, record_raw_capture, start_run

logger = logging.getLogger(__name__)

ALERT_AFTER_CONSECUTIVE_FAILURES = 2
FALLBACK_TTL_DAYS = 3


def _format_error_summary(errors: list, warnings: list, records_found: int) -> str:
    parts = []

    if errors:
        parts.append(f"{len(errors)} parse error(s)")
        for err in errors[:3]:
            parts.append(f"  • {err!s:.100}")

    if warnings:
        parts.append(f"{len(warnings)} warning(s)")
        parts.append(f"  ⚠ {str(warnings[0])[:100]}")

    if not errors and not warnings:
        return None

    return "; ".join(parts)[:500]


@dataclass(frozen=True)
class RecordingResult:
    status: str
    accepted: int
    flagged: int
    rejected: int
    duplicates: int
    candidates: int
    schema_changed: bool
    duration_ms: int
    error_code: Optional[str] = None
    error_summary: Optional[str] = None


def _store_raw_capture(conn, run_id: int, reason: str, raw_content: str) -> None:
    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()
    record_raw_capture(conn, run_id, reason, content_hash)


def _run_status(ingest_result) -> str:
    if ingest_result.rejected > 0 and ingest_result.accepted == 0:
        return "failed"
    if ingest_result.rejected > 0 or ingest_result.errors:
        return "partial_success"
    return "success"


def _reset_failure_counter(conn, source_id: int) -> None:
    RateSourceRepository(conn).reset_failure_counter(source_id)


def _increment_failure_counter(conn, source_id: int, error_code: str) -> bool:
    repo = RateSourceRepository(conn)
    consecutive, alert_sent_at = repo.increment_failure_counter(source_id, error_code)
    if consecutive >= ALERT_AFTER_CONSECUTIVE_FAILURES:
        if alert_sent_at is None or (
            datetime.now(timezone.utc) - alert_sent_at
        ).total_seconds() > 86400:
            return True
    return False


def _write_alert(conn, source_id: int, error_code: str, error_summary: str) -> None:
    RateSourceRepository(conn).write_alert(source_id, error_code, error_summary)


def _expire_stale_fallback_current(conn, source_id: int) -> None:
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
    errors: list = None,
    warnings: list = None,
) -> RecordingResult:
    repo = RateSourceRepository(conn)

    if schema_changed:
        new_fp = adapter.schema_fingerprint(raw_content)
        repo.update_schema_fingerprint(source_id, new_fp)

    fetched_at = datetime.now(timezone.utc)
    result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)

    if result.suspicious:
        _store_raw_capture(conn, run_id, "suspicious_data", raw_content)

    duration_ms = int((time.monotonic() - t0) * 1000)
    run_status = _run_status(result)

    errors = errors or []
    warnings = warnings or []
    error_summary = _format_error_summary(errors, warnings, len(records))

    finish_run(
        conn, run_id, run_status,
        http_status=http_status,
        records_found=len(records),
        records_accepted=result.accepted,
        records_flagged=result.flagged,
        records_duplicated=result.duplicates,
        duration_ms=duration_ms,
        is_fallback=False,
        error_summary=error_summary,
    )

    if run_status in ("success", "partial_success"):
        repo.update_last_success(source_id)
        _reset_failure_counter(conn, source_id)
        circuit_breaker.record_success(adapter_key)
        _expire_stale_fallback_current(conn, source_id)

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
    fallback_policy: FallbackPolicy,
) -> dict:
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

    af_res = fallback_policy.attempt(conn, source_id, adapter_key, user_agent)
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
    fetched_at = datetime.now(timezone.utc)
    result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)

    duration_ms = int((time.monotonic() - t0) * 1000)

    CollectionRunRepository(conn).finish_stale_run(
        run_id=run_id,
        records_found=len(records),
        records_accepted=result.accepted,
        records_flagged=result.flagged,
        records_duplicated=result.duplicates,
        duration_ms=duration_ms,
    )

    repo = RateSourceRepository(conn)
    repo.update_last_success(source_id)
    _reset_failure_counter(conn, source_id)

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
    fallback_policy: FallbackPolicy,
) -> dict:
    duration_ms = int((time.monotonic() - t0) * 1000)

    circuit_breaker.record_failure(adapter_key)

    if raw_content and error_code in ("parse_failure", "schema_change"):
        try:
            _store_raw_capture(conn, run_id, error_code, raw_content)
        except psycopg2.Error as exc:
            logger.warning("raw capture failed for run_id=%s: %s", run_id, exc)

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

    af_result = fallback_policy.attempt(conn, source_id, adapter_key, user_agent)
    if af_result:
        return af_result

    return {
        "source_id": source_id,
        "status": "failed",
        "error_code": error_code,
        "detail": error_summary,
    }
