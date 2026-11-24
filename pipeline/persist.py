import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from pipeline.fingerprint import FINGERPRINT_VERSION
from pipeline.normalize import normalize_currency_code
from domain.exceptions import StaleObservationError
from db.repositories.rate_observation_repository import RateObservationRepository

def insert_observation(
    conn,
    record: AdapterRecord,
    source_id: int,
    run_id: int,
    category_id: Optional[int],
    fingerprint: str,
    logical_key: Optional[str],
    identity_status: IdentityStatus,
    validation_status: ValidationStatus,
    validation_messages: list,
    fetched_at: datetime,
    version_number: Optional[int],
    is_current: bool,
    change_review_status: ChangeReviewStatus = ChangeReviewStatus.NOT_REQUIRED,
    supersedes_id: Optional[int] = None,
    is_fallback: bool = False,
) -> int:
    """Insert observation using repository pattern.
    
    This is a facade over RateObservationRepository.insert() for backward compatibility.
    """
    repo = RateObservationRepository(conn)
    return repo.insert(
        record=record,
        source_id=source_id,
        run_id=run_id,
        category_id=category_id,
        fingerprint=fingerprint,
        logical_key=logical_key,
        identity_status=identity_status,
        validation_status=validation_status,
        validation_messages=validation_messages,
        fetched_at=fetched_at,
        version_number=version_number,
        is_current=is_current,
        change_review_status=change_review_status,
        supersedes_id=supersedes_id,
        is_fallback=is_fallback,
    )

def insert_change_candidate(conn, observation_id: int, prior_version_id: int, source_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO change_candidate
                   (observation_id, prior_version_id, source_id, status)
               VALUES (%s, %s, %s, 'open')""",
            (observation_id, prior_version_id, source_id),
        )

def commit_correction(
    conn,
    prior_obs_id: int,
    record: AdapterRecord,
    source_id: int,
    run_id: int,
    category_id: Optional[int],
    fingerprint: str,
    logical_key: str,
    validation_status: ValidationStatus,
    validation_messages: list,
    fetched_at: datetime,
) -> int:
    """Commit a correction using repository pattern.
    
    This is a facade over RateObservationRepository methods for backward compatibility.
    """
    repo = RateObservationRepository(conn)
    
    # Lock and get version
    locked_version = repo.lock_and_get_version(prior_obs_id, logical_key)
    new_version = locked_version + 1
    
    # Insert correction
    new_id = repo.insert_correction(
        prior_obs_id=prior_obs_id,
        record=record,
        source_id=source_id,
        run_id=run_id,
        category_id=category_id,
        fingerprint=fingerprint,
        logical_key=logical_key,
        validation_status=validation_status,
        validation_messages=validation_messages,
        fetched_at=fetched_at,
        new_version=new_version,
    )
    
    # Demote prior observation and promote new one
    repo.demote_observation(prior_obs_id)
    repo.promote_observation(new_id)
    
    return new_id

def get_next_version_number(conn, logical_key: str) -> int:
    """Get next version number using repository pattern.
    
    This is a facade over RateObservationRepository.get_next_version_number() for backward compatibility.
    """
    repo = RateObservationRepository(conn)
    return repo.get_next_version_number(logical_key)
