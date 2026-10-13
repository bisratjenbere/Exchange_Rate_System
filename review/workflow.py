"""
review/workflow.py — change candidate decision recording.
LOCKED rules:
- A changed value is a review candidate, never an automatic correction.
- Only a confirmed correction creates a new version linked by supersedes_id.
- Dismissed candidate: keep audit record, exclude from trusted view.
- Decision records actor, time, and reason.
Gap review C: pending review on a logical observation shows uncertainty warning.
"""
from datetime import datetime, timezone
from typing import Optional

from pipeline.persist import commit_correction, get_next_version_number
from domain.records import AdapterRecord
from domain.enums import ValidationStatus


def decide_candidate(
    conn,
    candidate_id: int,
    decision: str,
    decided_by: str,
    decision_reason: str,
    # Required only for confirmed_correction:
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
    """
    Record a decision on a change_candidate.
    decision: confirmed_correction | new_publication | mapping_issue | dismissed

    For confirmed_correction: also commits the correction transaction and returns new obs id.
    For all others: updates candidate status and the observation's change_review_status.
    Returns new observation id for confirmed_correction, None otherwise.
    """
    valid_decisions = {"confirmed_correction", "new_publication", "mapping_issue", "dismissed"}
    if decision not in valid_decisions:
        raise ValueError(f"Invalid decision: {decision!r}")

    now = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        # Load candidate
        cur.execute(
            "SELECT observation_id, prior_version_id, source_id FROM change_candidate WHERE id=%s",
            (candidate_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"change_candidate {candidate_id} not found")
        obs_id, prior_version_id, cand_source_id = row

        # Update candidate
        cur.execute(
            """UPDATE change_candidate SET
                   status          = %s,
                   decision_reason = %s,
                   decided_at      = %s,
                   decided_by      = %s
               WHERE id = %s""",
            (decision, decision_reason, now, decided_by, candidate_id),
        )

        # Update observation's change_review_status
        cur.execute(
            "UPDATE rate_observation SET change_review_status=%s WHERE id=%s",
            (decision, obs_id),
        )

    if decision == "confirmed_correction":
        if not all([record, logical_key, fingerprint, fetched_at]):
            raise ValueError("confirmed_correction requires record, logical_key, fingerprint, fetched_at")

        # Get prior version number
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version_number FROM rate_observation WHERE id=%s",
                (prior_version_id,),
            )
            row = cur.fetchone()
            prior_version_number = row[0] if row and row[0] else 1

        conn.commit()
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
            prior_version_number=prior_version_number,
        )
        conn.commit()
        return new_id

    conn.commit()
    return None
