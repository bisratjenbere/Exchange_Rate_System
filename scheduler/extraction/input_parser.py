import logging
from dataclasses import dataclass

import psycopg2

from domain.fallback import FallbackPolicy
from domain.source import RateSource
from infrastructure.circuit_breaker import CircuitBreaker
from infrastructure.rate_source_repository import RateSourceRepository
from db.repositories.rate_observation_repository import RateObservationRepository
from pipeline.runs import recover_stuck_run, start_run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreflightResult:
    should_proceed: bool
    run_id: int | None = None
    early_return: dict | None = None
    source: RateSource | None = None


def validate_source_and_check_circuit_breaker(
    conn,
    source_id: int,
    circuit_breaker: CircuitBreaker,
    user_agent: str,
    fallback_policy: FallbackPolicy,
) -> PreflightResult:
    repo = RateSourceRepository(conn)
    source = repo.get_by_id(source_id)

    if source is None:
        return PreflightResult(
            should_proceed=False,
            early_return={"source_id": source_id, "status": "error", "detail": "source not found"},
        )

    adapter_key = source.adapter_key

    if not circuit_breaker.should_attempt(adapter_key):
        af_res = fallback_policy.attempt(conn, source_id, adapter_key, user_agent)
        if af_res is not None:
            return PreflightResult(should_proceed=False, early_return=af_res)

        return PreflightResult(
            should_proceed=False,
            early_return={
                "source_id": source_id,
                "status": "skipped",
                "detail": "circuit breaker open",
                "adapter_key": adapter_key,
            },
        )

    obs_repo = RateObservationRepository(conn)
    if obs_repo.has_fresh_observation_today(source_id):
        logger.debug("source=%s skipped — already has today's rate", source_id)
        return PreflightResult(
            should_proceed=False,
            early_return={
                "source_id": source_id,
                "status": "skipped",
                "detail": "already collected today",
            },
        )

    recover_stuck_run(conn, source_id)

    try:
        run_id = start_run(conn, source_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return PreflightResult(
            should_proceed=False,
            early_return={
                "source_id": source_id,
                "status": "skipped",
                "detail": "run already in progress",
            },
        )

    return PreflightResult(should_proceed=True, run_id=run_id, source=source)
