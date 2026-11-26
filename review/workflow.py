from datetime import datetime, timezone
from typing import Optional

from pipeline.persist import commit_correction
from domain.exceptions import StaleObservationError
from domain.records import AdapterRecord
from domain.enums import ValidationStatus
from db.repositories.change_candidate_repository import ChangeCandidateRepository
from db.repositories.rate_observation_repository import RateObservationRepository


def decide_candidate(
    conn,
    candidate_id: int,
    decision: str,
    decided_by: str,
    decision_reason: str,
    record: Optional[AdapterRecord] = None,
    source_id: Optional[int] = None,
    run_id: Optional[int] = None,
    category_id: Optional[int] = None,
    fingerprint: Optional[str] = None,
    logical_key: Optional[str] = None,
    validation_status: Optional[ValidationStatus] = None,
    validation_messages: Optional[list] = None,
    fetched_at: Optional[datetime] = None,
) -> Optional[int]:
    valid_decisions = {"confirmed_correction", "new_publication", "mapping_issue", "dismissed"}
    if decision not in valid_decisions:
        raise ValueError(f"Invalid decision: {decision!r}")

    candidate_repo = ChangeCandidateRepository(conn)
    observation_repo = RateObservationRepository(conn)
    now = datetime.now(timezone.utc)

    candidate = candidate_repo.get_by_id(candidate_id)
    if not candidate:
        raise ValueError(f"change_candidate {candidate_id} not found")
    
    obs_id = candidate["observation_id"]
    prior_version_id = candidate["prior_version_id"]
    cand_source_id = candidate["source_id"]

    # Update the candidate decision
    candidate_repo.update_status(
        candidate_id=candidate_id,
        status=decision,
        decision_reason=decision_reason,
        decided_at=now,
        decided_by=decided_by,
    )

    # Update the observation's review status
    observation_repo.update_change_review_status(obs_id, decision)

    if decision == "confirmed_correction":
        if not all([record, logical_key, fingerprint, fetched_at]):
            raise ValueError("confirmed_correction requires record, logical_key, fingerprint, fetched_at")

        new_id = commit_correction(
            conn=conn,
            prior_obs_id=prior_version_id,
            record=record,
            source_id=source_id or cand_source_id,
            run_id=run_id,
            category_id=category_id,
            fingerprint=fingerprint,
            logical_key=logical_key,
            validation_status=validation_status or ValidationStatus.VALIDATED,
            validation_messages=validation_messages or [],
            fetched_at=fetched_at,
        )
        conn.commit()
        return new_id

    conn.commit()
    return None
