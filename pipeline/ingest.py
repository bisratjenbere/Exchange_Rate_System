from dataclasses import dataclass, field, replace as dc_replace
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

MAX_INTRADAY_JUMP_PERCENT = 20.0

@dataclass
class IngestResult:
    accepted: int = 0
    flagged: int = 0
    rejected: int = 0
    duplicates: int = 0
    candidates: int = 0
    errors: list = field(default_factory=list)
    suspicious: bool = False

def ingest(conn, records: list, source_id: int, run_id: int,
           fetched_at: Optional[datetime] = None,
           is_fallback: bool = False) -> IngestResult:
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc)

    category_map = _load_category_map(conn)
    result = IngestResult()

    for record in records:
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT _ingest_sp")
        try:
            _process_one(conn, record, source_id, run_id, fetched_at,
                         category_map, result, is_fallback=is_fallback)
            with conn.cursor() as cur:
                cur.execute("RELEASE SAVEPOINT _ingest_sp")
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK TO SAVEPOINT _ingest_sp")
                cur.execute("RELEASE SAVEPOINT _ingest_sp")
            result.errors.append((record.source_currency_code, str(exc)))
            result.rejected += 1

    return result

def _process_one(conn, record, source_id, run_id, fetched_at,
                 category_map, result, is_fallback: bool = False):
    val_status, val_messages = validate(record)

    if any(m["code"] == "BUYING_ABOVE_SELLING" for m in val_messages):
        result.suspicious = True

    category_id = category_map.get(record.category)

    collection_date = fetched_at.date()
    fingerprint = compute_fingerprint(record, source_id, collection_date)

    logical_key, identity_status = build_identity(record, source_id,
                                                   fetched_date=fetched_at.date())

    if (record.effective_date is None
            and record.effective_date_basis == "collection_date_fallback"
            and identity_status == IdentityStatus.DERIVED):
        record = dc_replace(record, effective_date=fetched_at.date())

    if identity_status == IdentityStatus.AMBIGUOUS:
        action, existing_id = classify_ambiguous_observation(
            fingerprint, source_id,
            record.source_currency_code, record.category, conn,
        )
    else:
        action, existing_id = classify_observation(fingerprint, logical_key, conn)

    if action == "duplicate":
        if not is_fallback and record.effective_date is not None:
            _retire_prior_fallback_observations(conn, source_id, record.source_currency_code, record.effective_date)
        result.duplicates += 1
        return

    is_anomaly = False
    rate_delta = 0.0
    if action == "changed" and existing_id is not None:
        rate_delta = _get_rate_delta_percent(conn, existing_id, record)
        has_buying_above_selling = any(m.get("code") == "BUYING_ABOVE_SELLING" for m in val_messages)
        if has_buying_above_selling or rate_delta > MAX_INTRADAY_JUMP_PERCENT or val_status == ValidationStatus.REJECTED:
            is_anomaly = True

    if action == "new":
        version_number = (
            get_next_version_number(conn, logical_key)
            if logical_key and identity_status != IdentityStatus.AMBIGUOUS
            else None
        )
        is_current = (identity_status != IdentityStatus.AMBIGUOUS
                      and val_status != ValidationStatus.REJECTED)
        change_review_status = ChangeReviewStatus.NOT_REQUIRED
        supersedes_id = None

        if is_current:
            active = _get_active_observation(conn, source_id, record.source_currency_code, category_id)
            if active:
                _, active_eff_date, active_is_fallback = active
                if active_eff_date is not None and record.effective_date is not None:
                    if active_eff_date > record.effective_date:
                        is_current = False
                    elif is_fallback and active_eff_date == record.effective_date and not active_is_fallback:
                        is_current = False
                elif is_fallback and active_eff_date is not None and record.effective_date is None:
                    is_current = False

    elif action == "changed" and not is_anomaly:
        version_number = (
            get_next_version_number(conn, logical_key)
            if logical_key and identity_status != IdentityStatus.AMBIGUOUS
            else None
        )
        is_current = (identity_status != IdentityStatus.AMBIGUOUS
                      and val_status != ValidationStatus.REJECTED)
        change_review_status = ChangeReviewStatus.NOT_REQUIRED
        supersedes_id = existing_id

        if is_current and existing_id is not None:
            active = _get_active_observation(conn, source_id, record.source_currency_code, category_id)
            if active:
                _, active_eff_date, active_is_fallback = active
                if active_eff_date is not None and record.effective_date is not None:
                    if active_eff_date > record.effective_date:
                        is_current = False
                    elif is_fallback and active_eff_date == record.effective_date and not active_is_fallback:
                        is_current = False
                elif is_fallback and active_eff_date is not None and record.effective_date is None:
                    is_current = False

        if is_current and existing_id is not None:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rate_observation SET is_current = FALSE WHERE id = %s",
                    (existing_id,)
                )
        elif not is_current:
            supersedes_id = None

    else:
        version_number = None
        is_current = False
        change_review_status = ChangeReviewStatus.PENDING_REVIEW
        supersedes_id = None

    if is_current and action == "new":
        _retire_older_current(conn, source_id, record.source_currency_code, category_id)
        if record.effective_date is not None:
            _dismiss_superseded_candidates(conn, source_id, record.source_currency_code,
                                           category_id, record.effective_date, fetched_at)

    if is_current and not is_fallback and record.effective_date is not None:
        _retire_prior_fallback_observations(conn, source_id, record.source_currency_code, record.effective_date)

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
        supersedes_id=supersedes_id,
        is_fallback=is_fallback,
    )

    if action == "changed" and is_anomaly and existing_id is not None:
        if not _is_same_rate(conn, obs_id, existing_id):
            insert_change_candidate(conn, obs_id, existing_id, source_id)
            result.candidates += 1

    if val_status == ValidationStatus.REJECTED:
        result.rejected += 1
    elif (action == "changed" and is_anomaly) or val_status == ValidationStatus.WARNING or identity_status == IdentityStatus.AMBIGUOUS:
        result.flagged += 1
    else:
        result.accepted += 1

def _load_category_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT code, id FROM rate_category WHERE is_active = TRUE")
        return {row[0]: row[1] for row in cur.fetchall()}

def _retire_older_current(conn, source_id: int, currency_code: str, category_id):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_observation
               SET is_current = FALSE
               WHERE source_id = %s
                 AND source_currency_code = %s
                 AND category_id IS NOT DISTINCT FROM %s
                 AND is_current = TRUE""",
            (source_id, currency_code, category_id),
        )

def _retire_prior_fallback_observations(conn, source_id: int, currency_code: str, effective_date):
    if effective_date is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_observation
               SET is_current = FALSE
               WHERE source_id = %s
                 AND source_currency_code = %s
                 AND is_current = TRUE
                 AND (is_fallback = TRUE OR effective_date < %s)""",
            (source_id, currency_code, effective_date),
        )

def _dismiss_superseded_candidates(conn, source_id: int, currency_code: str,
                                   category_id, effective_date, fetched_at: datetime):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE change_candidate cc
               SET status = 'dismissed',
                   decision_reason = 'superseded_by_newer_publication',
                   decided_at = %s,
                   decided_by = 'system'
               FROM rate_observation ro
               WHERE cc.observation_id = ro.id
                 AND ro.source_id = %s
                 AND ro.source_currency_code = %s
                 AND ro.category_id IS NOT DISTINCT FROM %s
                 AND cc.status = 'open'
                 AND ro.effective_date < %s""",
            (fetched_at, source_id, currency_code, category_id, effective_date),
        )

def _is_same_rate(conn, obs_id: int, prior_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT
                 (a.buying_rate IS NOT DISTINCT FROM b.buying_rate)
                 AND (a.selling_rate IS NOT DISTINCT FROM b.selling_rate)
               FROM rate_observation a, rate_observation b
               WHERE a.id = %s AND b.id = %s""",
            (obs_id, prior_id),
        )
        row = cur.fetchone()
        return bool(row and row[0])

def _get_rate_delta_percent(conn, existing_id: int, record) -> float:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT buying_rate, selling_rate FROM rate_observation WHERE id = %s",
            (existing_id,)
        )
        row = cur.fetchone()
        if not row:
            return 0.0
        old_buy, old_sell = row[0], row[1]
        deltas = []
        if old_buy is not None and record.buying_rate is not None and float(old_buy) > 0:
            deltas.append(abs(float(record.buying_rate) - float(old_buy)) / float(old_buy) * 100.0)
        if old_sell is not None and record.selling_rate is not None and float(old_sell) > 0:
            deltas.append(abs(float(record.selling_rate) - float(old_sell)) / float(old_sell) * 100.0)
        return max(deltas) if deltas else 0.0

def _get_active_observation(conn, source_id: int, currency_code: str, category_id):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, effective_date, is_fallback
               FROM rate_observation
               WHERE source_id = %s
                 AND source_currency_code = %s
                 AND category_id IS NOT DISTINCT FROM %s
                 AND is_current = TRUE
               LIMIT 1""",
            (source_id, currency_code, category_id)
        )
        return cur.fetchone()
