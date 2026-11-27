import logging
import time
from datetime import datetime, timezone

import psycopg2
import requests

from domain.fallback import FallbackPolicy
from pipeline.ingest import ingest
from pipeline.runs import finish_run
from infrastructure.rate_source_repository import RateSourceRepository
from scheduler.extraction.input_parser import validate_source_and_check_circuit_breaker
from scheduler.extraction.fetcher import fetch_parse_and_check_schema
from scheduler.extraction.decision import classify_records
from scheduler.extraction.recorder import (
    record_failed_with_fallback_attempt,
    record_stale_retained,
    record_normal_success,
    record_exception,
)

logger = logging.getLogger(__name__)


def run_source_orchestrated(
    conn,
    source_id: int,
    circuit_breaker,
    adapter_registry,
    error_classifier,
    user_agent: str,
    fallback_policy: FallbackPolicy,
    dry_run: bool = False,
) -> dict:

    preflight = validate_source_and_check_circuit_breaker(
        conn, source_id, circuit_breaker, user_agent, fallback_policy
    )

    if not preflight.should_proceed:
        return preflight.early_return

    run_id = preflight.run_id
    source = preflight.source
    adapter_key = source.adapter_key

    repo = RateSourceRepository(conn)

    t0 = time.monotonic()
    raw_content: str | None = None
    http_status: int | None = None
    schema_changed: bool = False

    try:
        fetch_result = fetch_parse_and_check_schema(
            conn, run_id, source, adapter_registry, repo, user_agent
        )

        records = fetch_result.records
        raw_content = fetch_result.raw_content
        http_status = fetch_result.http_status
        schema_changed = fetch_result.schema_changed
        adapter = fetch_result.adapter
        errors = fetch_result.errors
        warnings = fetch_result.warnings

        decision = classify_records(records)

        if decision.classification in ("zero", "stale"):
            result = record_failed_with_fallback_attempt(
                conn, run_id, source_id,
                error_code=decision.error_code,
                error_summary=decision.error_summary,
                http_status=http_status,
                records_count=len(records),
                t0=t0,
                adapter_key=adapter_key,
                user_agent=user_agent,
                fallback_policy=fallback_policy,
            )
            conn.commit()

            if result.get("is_fallback"):
                return result

            if decision.classification == "stale":
                result = record_stale_retained(
                    conn, run_id, source_id, records, raw_content, http_status, t0
                )
                conn.commit()
                return result

            return result

        if dry_run:
            fetched_at = datetime.now(timezone.utc)
            result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)
            duration_ms = int((time.monotonic() - t0) * 1000)
            finish_run(
                conn, run_id, "dry_run",
                records_found=len(records),
                records_accepted=result.accepted,
                duration_ms=duration_ms,
            )
            conn.rollback()
            return {
                "source_id": source_id,
                "status": "dry_run",
                "records_found": len(records),
                "would_accept": result.accepted,
                "would_reject": result.rejected,
                "would_flag": result.flagged,
                "would_duplicate": result.duplicates,
                "schema_changed": schema_changed,
                "duration_ms": duration_ms,
            }

        recording_result = record_normal_success(
            conn, run_id, source_id, records, raw_content, http_status,
            adapter, schema_changed, t0, circuit_breaker, adapter_key,
            errors, warnings,
        )
        conn.commit()

        return {
            "source_id": source_id,
            "status": recording_result.status,
            "accepted": recording_result.accepted,
            "flagged": recording_result.flagged,
            "rejected": recording_result.rejected,
            "duplicates": recording_result.duplicates,
            "candidates": recording_result.candidates,
            "schema_changed": recording_result.schema_changed,
        }

    except (OSError, RuntimeError, ValueError, KeyError,
            requests.exceptions.RequestException, psycopg2.Error) as exc:
        error_code, error_summary = error_classifier.classify(exc)
        result = record_exception(
            conn, run_id, source_id, error_code, error_summary,
            raw_content, http_status, t0, circuit_breaker,
            adapter_key, user_agent, fallback_policy,
        )
        try:
            conn.commit()
        except psycopg2.Error:
            conn.rollback()
        return result
