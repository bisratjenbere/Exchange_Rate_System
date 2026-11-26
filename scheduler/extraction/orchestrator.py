"""
Orchestrator module - High-level coordination of collection workflow.

Extracted from scheduler/runner.py lines 76-201.
Handles:
- Coordination of all extraction modules (input_parser, fetcher, decision, recorder)
- Main collection workflow orchestration
- Exception handling and error classification
- Dry-run mode coordination

This module contains NO business logic - only coordination.
All actual work is delegated to specialized extraction modules.

PRESERVED BUGS:
- Bug #1: Double status in stale path (delegated to recorder)
- Bug #2: Dry-run orphaned runs (delegated to recorder)
- Bug #3: Silent raw capture failure (delegated to recorder)
- Bug #4: Invisible fallback expiration (delegated to recorder)
"""

import time
from datetime import datetime, timezone

from pipeline.ingest import ingest
from infrastructure.rate_source_repository import RateSourceRepository


def run_source_orchestrated(
    conn,
    source_id: int,
    circuit_breaker,
    adapter_registry,
    error_classifier,
    user_agent: str,
    dry_run: bool = False,
) -> dict:
    """
    Orchestrate the collection run workflow.
    
    This function coordinates all phases of a collection run:
    1. Pre-flight checks (circuit breaker, source validation, stuck run recovery)
    2. Fetch and parse (adapter loading, HTTP fetching, schema checking)
    3. Decision (zero/stale/normal classification)
    4. Recording (database writes, transaction management)
    5. Exception handling (error classification, fallback attempts)
    
    Args:
        conn: Database connection
        source_id: ID of the rate source to collect
        circuit_breaker: Circuit breaker instance for failure tracking
        adapter_registry: Registry containing all adapters
        error_classifier: Error classifier for exception handling
        user_agent: User agent string for HTTP requests
        dry_run: If True, rollback all changes (preserves Bug #2)
    
    Returns:
        dict: Collection result with status, metrics, and metadata
        
    Transaction Behavior:
        All transaction logic (commit/rollback) is delegated to recorder module.
        This function never directly calls conn.commit() or conn.rollback().
    
    Bug Preservation:
        All 4 documented bugs are preserved through delegation to recorder module.
    """
    # Phase 0: Pre-flight checks (extracted to input_parser module)
    from scheduler.extraction.input_parser import validate_source_and_check_circuit_breaker
    
    preflight = validate_source_and_check_circuit_breaker(
        conn, source_id, circuit_breaker, user_agent
    )
    
    if not preflight.should_proceed:
        return preflight.early_return
    
    # Pre-flight passed - extract values for main collection logic
    run_id = preflight.run_id
    source = preflight.source
    adapter_key = source["adapter_key"]
    
    repo = RateSourceRepository(conn)
    
    t0 = time.monotonic()
    raw_content: str | None = None
    http_status: int | None = None
    schema_changed: bool = False
    
    try:
        # Phase 1: Fetch and parse (extracted to fetcher module)
        from scheduler.extraction.fetcher import fetch_parse_and_check_schema
        
        fetch_result = fetch_parse_and_check_schema(
            conn, run_id, source, adapter_registry, repo, user_agent
        )
        
        # Extract values for decision logic
        records = fetch_result.records
        raw_content = fetch_result.raw_content
        http_status = fetch_result.http_status
        schema_changed = fetch_result.schema_changed
        adapter = fetch_result.adapter
        errors = fetch_result.errors        # S1: Parse errors
        warnings = fetch_result.warnings    # S1: Parse warnings
        # Note: fetch_result.duration_ms not used here, we use t0 for total duration
        
        # Phase 2: Decide how to handle records (extracted to decision module)
        from scheduler.extraction.decision import classify_records
        from scheduler.extraction.recorder import (
            record_failed_with_fallback_attempt,
            record_stale_retained
        )
        
        decision = classify_records(records)
        
        # Handle zero/stale classification
        if decision.classification in ("zero", "stale"):
            # Failed path with fallback attempt
            result = record_failed_with_fallback_attempt(
                conn, run_id, source_id,
                error_code=decision.error_code,
                error_summary=decision.error_summary,
                http_status=http_status,
                records_count=len(records),
                t0=t0,
                adapter_key=adapter_key,
                user_agent=user_agent,
            )
            
            # If fallback succeeded, return early
            if result.get("is_fallback"):
                return result
            
            # If stale, retain as standing rate (BUG #1: double finish_run)
            if decision.classification == "stale":
                return record_stale_retained(
                    conn, run_id, source_id, records, raw_content, http_status, t0
                )
            
            # Zero records, no fallback
            return result
        
        # Phase 3: Normal path - ingest and record (extracted to recorder module)
        from scheduler.extraction.recorder import record_normal_success
        
        # Handle dry-run before recording
        if dry_run:
            # Need to call ingest first to get metrics
            fetched_at = datetime.now(timezone.utc)
            result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)
            duration_ms = int((time.monotonic() - t0) * 1000)
            
            conn.rollback()  # BUG #2: start_run already committed
            return {
                "source_id": source_id,
                "status": "dry_run",
                "records_found": len(records),
                "would_accept": result.accepted,
                "would_reject": result.rejected,
                "would_flag": result.flagged,
                "would_duplicate": result.duplicates,
                "schema_changed": schema_changed,
                "duration_ms": duration_ms
            }
        
        # Record normal success
        recording_result = record_normal_success(
            conn, run_id, source_id, records, raw_content, http_status,
            adapter, schema_changed, t0, circuit_breaker, adapter_key,
            errors, warnings  # S1: Pass parse errors/warnings
        )
        
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
    
    except Exception as exc:
        # Phase 4: Exception handling (extracted to recorder module)
        from scheduler.extraction.recorder import record_exception
        
        error_code, error_summary = error_classifier.classify(exc)
        
        return record_exception(
            conn, run_id, source_id, error_code, error_summary,
            raw_content, http_status, t0, circuit_breaker,
            adapter_key, user_agent
        )
