"""
pipeline/ingest.py — connects adapter output to the full pipeline.

Takes a list of AdapterRecord objects and runs them through:
  validate → fingerprint → identity → deduplicate → persist

Returns IngestResult with counts for finish_run.
Triggers record_raw_capture for schema_change and suspicious_data.

LOCKED rules:
- Rejected records are stored (not silently dropped) with validation_status=rejected.
- Changed values → change_candidate, never automatic correction.
- Ambiguous identity retained and flagged.
- category_id resolved from rate_category table; NULL for UNKNOWN.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from domain.records import UNKNOWN_CATEGORY
from pipeline.validate import validate
from pipeline.fingerprint import compute_fingerprint
from pipeline.identity import build_identity
from pipeline.deduplicate import classify_observation, classify_ambiguous_observation
from pipeline.persist import (
    insert_observation,
    insert_change_candidate,
    get_next_version_number,
)


@dataclass
class IngestResult:
    accepted: int = 0
    flagged: int = 0      # warnings or ambiguous identity
    rejected: int = 0
    duplicates: int = 0
    candidates: int = 0   # change_candidate rows created
    errors: list = field(default_factory=list)   # (currency, reason) pairs
    suspicious: bool = False   # any BUYING_ABOVE_SELLING seen


def ingest(conn, records: list, source_id: int, run_id: int,
           fetched_at: Optional[datetime] = None) -> IngestResult:
    """
    Process a list of AdapterRecord objects through the full pipeline.
    All DB writes happen inside this function; caller commits.
    """
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc)

    category_map = _load_category_map(conn)
    result = IngestResult()

    for record in records:
        try:
            _process_one(conn, record, source_id, run_id, fetched_at,
                         category_map, result)
        except Exception as exc:
            result.errors.append((record.source_currency_code, str(exc)))
            result.rejected += 1

    return result


def _process_one(conn, record, source_id, run_id, fetched_at,
                 category_map, result):
    # 1. Validate
    val_status, val_messages = validate(record)

    # Track suspicious data for raw_capture trigger
    if any(m["code"] == "BUYING_ABOVE_SELLING" for m in val_messages):
        result.suspicious = True

    # 2. Resolve category_id (NULL for UNKNOWN — excluded from trusted view)
    category_id = category_map.get(record.category)  # None if UNKNOWN

    # 3. Fingerprint
    fingerprint = compute_fingerprint(record, source_id)

    # 4. Identity
    logical_key, identity_status = build_identity(record, source_id)

    # 5. Deduplicate
    if identity_status == IdentityStatus.AMBIGUOUS:
        action, existing_id = classify_ambiguous_observation(
            fingerprint, source_id,
            record.source_currency_code, record.category, conn,
        )
    else:
        action, existing_id = classify_observation(fingerprint, logical_key, conn)

    if action == "duplicate":
        result.duplicates += 1
        return

    # 6. Determine version and review status
    if action == "new":
        version_number = (
            get_next_version_number(conn, logical_key)
            if logical_key and identity_status != IdentityStatus.AMBIGUOUS
            else None
        )
        is_current = (identity_status != IdentityStatus.AMBIGUOUS
                      and val_status != ValidationStatus.REJECTED)
        change_review_status = ChangeReviewStatus.NOT_REQUIRED

    else:  # changed
        version_number = None   # candidate — no committed version yet
        is_current = False
        change_review_status = ChangeReviewStatus.PENDING_REVIEW

    # 7. Insert observation
    obs_id = insert_observation(
        conn=conn,
        record=record,
        source_id=source_id,
        run_id=run_id,
        category_id=category_id,
        fingerprint=fingerprint,
        logical_key=logical_key,
        identity_status=identity_status,
        validation_status=val_status,
        validation_messages=val_messages,
        fetched_at=fetched_at,
        version_number=version_number,
        is_current=is_current,
        change_review_status=change_review_status,
    )

    # 8. Create change_candidate for changed observations
    if action == "changed" and existing_id is not None:
        insert_change_candidate(conn, obs_id, existing_id, source_id)
        result.candidates += 1

    # 9. Update counts
    if val_status == ValidationStatus.REJECTED:
        result.rejected += 1
    elif (action == "changed"
          or val_status == ValidationStatus.WARNING
          or identity_status == IdentityStatus.AMBIGUOUS
          or category_id is None):
        result.flagged += 1
    else:
        result.accepted += 1


def _load_category_map(conn) -> dict:
    """Return {code: id} for all active rate_category rows."""
    with conn.cursor() as cur:
        cur.execute("SELECT code, id FROM rate_category WHERE is_active = TRUE")
        return {row[0]: row[1] for row in cur.fetchall()}
