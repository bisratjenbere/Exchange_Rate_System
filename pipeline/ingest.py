from dataclasses import dataclass, field, replace as dc_replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import logging
import threading
import time

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
from db.repositories.rate_observation_repository import RateObservationRepository
from db.repositories.change_candidate_repository import ChangeCandidateRepository
from db.repositories.rate_category_repository import RateCategoryRepository

logger = logging.getLogger(__name__)

MAX_INTRADAY_JUMP_PERCENT = 20.0

SAVEPOINT_BATCH_SIZE = 10

_category_map_cache = None
_cache_timestamp = None
_cache_lock = threading.Lock()
CATEGORY_CACHE_TTL = 300  # 5 minutes in seconds

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

    # Process in batches for better performance
    total_records = len(records)

    for batch_start in range(0, total_records, SAVEPOINT_BATCH_SIZE):
        batch = records[batch_start:batch_start + SAVEPOINT_BATCH_SIZE]

        if not _process_batch_optimistic(
            conn, batch, source_id, run_id, fetched_at,
            category_map, result, is_fallback
        ):
            _process_batch_individually(
                conn, batch, source_id, run_id, fetched_at,
                category_map, result, is_fallback
            )

    # Suspicious data check (unchanged)
    by_currency = {}
    for record in records:
        by_currency.setdefault(record.source_currency_code, []).append(record)

    for curr, recs in by_currency.items():
        cash_rec = next((r for r in recs if r.category == "cash"), None)
        txn_rec = next((r for r in recs if r.category == "transactional"), None)
        if cash_rec and txn_rec and cash_rec.buying_rate is not None and txn_rec.buying_rate is not None:
            if cash_rec.buying_rate < (txn_rec.buying_rate - Decimal("0.05")):
                result.suspicious = True

    return result


def _process_batch_optimistic(
    conn, batch, source_id, run_id, fetched_at,
    category_map, result, is_fallback
) -> bool:
    savepoint_name = f"_batch_{id(batch)}"

    try:
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {savepoint_name}")

        for record in batch:
            _process_one(
                conn, record, source_id, run_id, fetched_at,
                category_map, result, is_fallback
            )

        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")

        return True

    except Exception:
        try:
            with conn.cursor() as cur:
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except Exception:
            pass

        return False


def _process_batch_individually(
    conn, batch, source_id, run_id, fetched_at,
    category_map, result, is_fallback
):
    for record in batch:
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT _ingest_sp")
        try:
            _process_one(
                conn, record, source_id, run_id, fetched_at,
                category_map, result, is_fallback
            )
            with conn.cursor() as cur:
                cur.execute("RELEASE SAVEPOINT _ingest_sp")
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK TO SAVEPOINT _ingest_sp")
                cur.execute("RELEASE SAVEPOINT _ingest_sp")
            result.errors.append((record.source_currency_code, str(exc)))
            result.rejected += 1

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
        if not is_fallback:
            if record.effective_date is not None:
                _retire_prior_fallback_observations(conn, source_id, record.source_currency_code, category_id, record.effective_date, is_fallback=False)
            if existing_id is not None:
                # Promote fallback to non-fallback using repository
                repo = RateObservationRepository(conn)
                repo.promote_fallback_to_non_fallback(existing_id)
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
            # Demote existing observation using repository
            repo = RateObservationRepository(conn)
            repo.demote_observation(existing_id)
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

    if is_current and record.effective_date is not None:
        _retire_prior_fallback_observations(conn, source_id, record.source_currency_code, category_id, record.effective_date, is_fallback=is_fallback)

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
    global _category_map_cache, _cache_timestamp

    now = time.time()
    if _category_map_cache is not None and _cache_timestamp is not None:
        if now - _cache_timestamp < CATEGORY_CACHE_TTL:
            return _category_map_cache

    with _cache_lock:
        if _category_map_cache is not None and _cache_timestamp is not None:
            if now - _cache_timestamp < CATEGORY_CACHE_TTL:
                return _category_map_cache
        repo = RateCategoryRepository(conn)
        _category_map_cache = repo.get_active_categories_map()
        _cache_timestamp = time.time()

    return _category_map_cache

def _retire_older_current(conn, source_id: int, currency_code: str, category_id):
    repo = RateObservationRepository(conn)
    repo.retire_current_observations(source_id, currency_code, category_id)

def _retire_prior_fallback_observations(conn, source_id: int, currency_code: str, category_id, effective_date, is_fallback: bool = False):
    if effective_date is None:
        return
    repo = RateObservationRepository(conn)
    repo.retire_prior_fallback_observations(source_id, currency_code, category_id, effective_date, is_fallback)

def _dismiss_superseded_candidates(conn, source_id: int, currency_code: str,
                                   category_id, effective_date, fetched_at: datetime):
    repo = ChangeCandidateRepository(conn)
    repo.dismiss_superseded_by_date(
        source_id=source_id,
        currency_code=currency_code,
        category_id=category_id,
        effective_date=effective_date,
        decided_at=fetched_at,
        decided_by='system'
    )

def _is_same_rate(conn, obs_id: int, prior_id: int) -> bool:
    repo = RateObservationRepository(conn)
    return repo.compare_rates(obs_id, prior_id)

def _get_rate_delta_percent(conn, existing_id: int, record) -> float:
    repo = RateObservationRepository(conn)
    row = repo.get_rates_for_comparison(existing_id)
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
    repo = RateObservationRepository(conn)
    obs = repo.get_active_observation(source_id, currency_code, category_id)
    if obs:
        return (obs['id'], obs['effective_date'], obs['is_fallback'])
    return None
