"""
Input parser module - Pre-flight checks and source validation.

Extracted from scheduler/runner.py lines 76-101.
Handles:
- Source loading and validation
- Circuit breaker checks
- Stuck run recovery (side effect)
- Concurrent run detection

This module contains NO transaction logic (except recover_stuck_run which manages its own).
"""

from dataclasses import dataclass

import psycopg2

from infrastructure.circuit_breaker import CircuitBreaker
from infrastructure.rate_source_repository import RateSourceRepository
from pipeline.runs import recover_stuck_run, start_run


@dataclass(frozen=True)
class PreflightResult:
    """Result of pre-flight checks before starting a collection run."""
    should_proceed: bool
    run_id: int | None = None
    early_return: dict | None = None  # If should_proceed=False, this contains the return dict
    source: dict | None = None  # Source record from DB if validation passed


def validate_source_and_check_circuit_breaker(
    conn,
    source_id: int,
    circuit_breaker: CircuitBreaker,
    user_agent: str,
) -> PreflightResult:
    """
    Perform pre-flight checks before starting a collection run.

    Steps:
    1. Load source from database
    2. Validate source exists
    3. Check circuit breaker
    4. Recover any stuck runs (side effect)
    5. Start a new run (or detect concurrent run)

    Args:
        conn: Database connection
        source_id: ID of the source to collect
        circuit_breaker: Circuit breaker instance
        user_agent: User agent string for fallback attempts

    Returns:
        PreflightResult indicating whether to proceed and any early return values

    Transaction Behavior:
        - Mostly read-only
        - recover_stuck_run() commits internally
        - start_run() commits internally
        - conn.rollback() if UniqueViolation (concurrent run)
    """
    repo = RateSourceRepository(conn)
    source = repo.get_by_id(source_id)

    # Check 1: Source exists
    if source is None:
        return PreflightResult(
            should_proceed=False,
            early_return={"source_id": source_id, "status": "error", "detail": "source not found"}
        )

    adapter_key = source["adapter_key"]

    # Check 2: Circuit breaker
    if not circuit_breaker.should_attempt(adapter_key):
        # Try fallback first
        from scheduler.runner import _try_af_fallback  # Import here to avoid circular dependency
        af_res = _try_af_fallback(conn, source_id, adapter_key, user_agent)
        if af_res is not None:
            return PreflightResult(should_proceed=False, early_return=af_res)

        # No fallback available
        return PreflightResult(
            should_proceed=False,
            early_return={
                "source_id": source_id,
                "status": "skipped",
                "detail": "circuit breaker open",
                "adapter_key": adapter_key
            }
        )

    # Side effect: Recover any stuck runs before starting new one
    recover_stuck_run(conn, source_id)

    # Check 3: Start run (or detect concurrent run)
    try:
        run_id = start_run(conn, source_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return PreflightResult(
            should_proceed=False,
            early_return={
                "source_id": source_id,
                "status": "skipped",
                "detail": "run already in progress"
            }
        )

    # All checks passed - proceed with collection
    return PreflightResult(
        should_proceed=True,
        run_id=run_id,
        source=source
    )
