import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from pipeline.fingerprint import FINGERPRINT_VERSION
from pipeline.normalize import normalize_currency_code

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
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rate_observation (
                   source_id, collection_run_id, category_id,
                   currency_code, source_currency_code, currency_name,
                   buying_rate, selling_rate, source_rate_text, source_excerpt,
                   quote_currency_code, unit_multiplier,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   version_number, is_current, identity_status,
                   validation_status, validation_messages,
                   change_review_status, logical_observation_key,
                   supersedes_id, is_fallback
               ) VALUES (
                   %s, %s, %s,
                   %s, %s, %s,
                   %s, %s, %s, %s,
                   %s, %s,
                   %s, %s,
                   %s, %s, %s,
                   %s, %s, %s,
                   %s, %s,
                   %s, %s,
                   %s, %s
               ) RETURNING id""",
            (
                source_id, run_id, category_id,
                normalize_currency_code(record.source_currency_code),
                record.source_currency_code, record.currency_name,
                record.buying_rate, record.selling_rate,
                record.source_rate_text,
                json.dumps(record.raw_excerpt) if record.raw_excerpt else None,
                record.quote_currency_code, record.unit_multiplier,
                record.effective_date, record.effective_date_basis,
                fetched_at, fingerprint, FINGERPRINT_VERSION,
                version_number, is_current, identity_status.value,
                validation_status.value,
                json.dumps(validation_messages) if validation_messages else None,
                change_review_status.value, logical_key,
                supersedes_id, is_fallback,
            ),
        )
        return cur.fetchone()[0]

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
    prior_version_number: int,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, logical_observation_key FROM rate_observation WHERE id = %s FOR UPDATE",
            (prior_obs_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Prior observation {prior_obs_id} not found")
        if row[1] != logical_key:
            raise ValueError("Logical key mismatch — cannot correct across different observations")

        new_version = prior_version_number + 1

        cur.execute(
            """INSERT INTO rate_observation (
                   source_id, collection_run_id, category_id,
                   currency_code, source_currency_code, currency_name,
                   buying_rate, selling_rate, source_rate_text, source_excerpt,
                   quote_currency_code, unit_multiplier,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   version_number, is_current, identity_status,
                   validation_status, validation_messages,
                   change_review_status, logical_observation_key,
                   supersedes_id
               ) VALUES (
                   %s, %s, %s,
                   %s, %s, %s,
                   %s, %s, %s, %s,
                   %s, %s,
                   %s, %s,
                   %s, %s, %s,
                   %s, FALSE, 'confirmed',
                   %s, %s,
                   'confirmed_correction', %s,
                   %s
               ) RETURNING id""",
            (
                source_id, run_id, category_id,
                normalize_currency_code(record.source_currency_code),
                record.source_currency_code, record.currency_name,
                record.buying_rate, record.selling_rate,
                record.source_rate_text,
                json.dumps(record.raw_excerpt) if record.raw_excerpt else None,
                record.quote_currency_code, record.unit_multiplier,
                record.effective_date, record.effective_date_basis,
                fetched_at, fingerprint, FINGERPRINT_VERSION,
                new_version,
                validation_status.value,
                json.dumps(validation_messages) if validation_messages else None,
                logical_key,
                prior_obs_id,
            ),
        )
        new_id = cur.fetchone()[0]

        cur.execute(
            "UPDATE rate_observation SET is_current = FALSE WHERE id = %s",
            (prior_obs_id,),
        )
        cur.execute(
            "UPDATE rate_observation SET is_current = TRUE WHERE id = %s",
            (new_id,),
        )
    return new_id

def get_next_version_number(conn, logical_key: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(MAX(version_number), 0)
               FROM rate_observation
               WHERE logical_observation_key = %s AND version_number IS NOT NULL""",
            (logical_key,),
        )
        return cur.fetchone()[0] + 1
