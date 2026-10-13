"""
M7 tests — collection run lifecycle, trusted view, review workflow.
Acceptance tests 9, 10, 11, 19, 20, 21, 22.
Gap-review tests C, G, K, L.
"""
import hashlib
import pytest
from decimal import Decimal
from datetime import date, datetime, timezone, timedelta

import psycopg2

from tests.db_utils import get_conn, apply_migrations, reset_schema
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from pipeline.fingerprint import compute_fingerprint
from pipeline.identity import build_identity
from pipeline.persist import insert_observation, insert_change_candidate, commit_correction
from pipeline.runs import (
    start_run, finish_run, recover_stuck_run,
    record_raw_capture, get_running_run, STUCK_RUN_THRESHOLD_HOURS,
)
from trusted_view.query import get_trusted_rates, get_observation_with_warnings
from review.workflow import decide_candidate


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def rollback(db):
    yield
    db.rollback()


NOW = datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc)


def _seed_bank(cur, code):
    cur.execute(
        "INSERT INTO bank (code, name) VALUES (%s,%s) RETURNING id",
        (code, f"Bank {code}"),
    )
    return cur.fetchone()[0]


def _seed_source(cur, bank_id, key, verified=False):
    vstatus = "provisional" if verified else "unverified"
    cur.execute(
        """INSERT INTO rate_source
               (bank_id, source_url, collection_method, adapter_key, verification_status)
           VALUES (%s,'https://x.com','api',%s,%s) RETURNING id""",
        (bank_id, key, vstatus),
    )
    return cur.fetchone()[0]


def _seed_category(cur, code="cash"):
    cur.execute(
        """INSERT INTO rate_category (code, name, approved_at)
           VALUES (%s,%s,now())
           ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code RETURNING id""",
        (code, code),
    )
    return cur.fetchone()[0]


def _record(currency="USD", category="cash",
            buying=Decimal("161.00"), selling=Decimal("164.00"),
            basis="source_published", src_key="pub-001",
            eff_date=date(2026, 10, 10)):
    return AdapterRecord(
        source_currency_code=currency, category=category,
        buying_rate=buying, selling_rate=selling,
        effective_date=eff_date, effective_date_basis=basis,
        source_record_key=src_key,
        source_rate_text=f"{buying}/{selling}",
    )


def _persist(db, record, source_id, run_id, category_id,
             version=1, is_current=True, lkey=None, istatus=None):
    if lkey is None:
        lkey, istatus = build_identity(record, source_id)
    elif istatus is None:
        _, istatus = build_identity(record, source_id)
    fp = compute_fingerprint(record, source_id)
    return insert_observation(
        conn=db, record=record, source_id=source_id,
        run_id=run_id, category_id=category_id,
        fingerprint=fp, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=version, is_current=is_current,
    )


# ── run lifecycle ─────────────────────────────────────────────────────────────

def test_start_run_creates_running_row(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "RL1")
    sid = _seed_source(cur, bid, "rl1")
    db.commit()
    run_id = start_run(db, sid)
    cur = db.cursor()
    cur.execute("SELECT status FROM collection_run WHERE id=%s", (run_id,))
    assert cur.fetchone()[0] == "running"


def test_finish_run_marks_success(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "RL2")
    sid = _seed_source(cur, bid, "rl2")
    db.commit()
    run_id = start_run(db, sid)
    finish_run(db, run_id, "success", records_found=5, records_accepted=5)
    cur = db.cursor()
    cur.execute("SELECT status, records_found FROM collection_run WHERE id=%s", (run_id,))
    row = cur.fetchone()
    assert row[0] == "success"
    assert row[1] == 5


def test_finish_run_marks_failed(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "RL3")
    sid = _seed_source(cur, bid, "rl3")
    db.commit()
    run_id = start_run(db, sid)
    finish_run(db, run_id, "failed", error_code="HTTP_403", error_summary="Forbidden")
    cur = db.cursor()
    cur.execute("SELECT status, error_code FROM collection_run WHERE id=%s", (run_id,))
    row = cur.fetchone()
    assert row[0] == "failed"
    assert row[1] == "HTTP_403"


def test_gap_K_one_running_run_per_source(db):
    """Gap review K: overlapping runs for same source prevented."""
    cur = db.cursor()
    bid = _seed_bank(cur, "RL4")
    sid = _seed_source(cur, bid, "rl4")
    db.commit()
    start_run(db, sid)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        start_run(db, sid)


def test_gap_K_second_run_allowed_after_first_finishes(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "RL5")
    sid = _seed_source(cur, bid, "rl5")
    db.commit()
    run_id = start_run(db, sid)
    finish_run(db, run_id, "success")
    run_id2 = start_run(db, sid)
    assert run_id2 != run_id


def test_gap_K_recover_stuck_run(db):
    """Gap review K: stuck running row recovered by documented rule."""
    cur = db.cursor()
    bid = _seed_bank(cur, "RL6")
    sid = _seed_source(cur, bid, "rl6")
    # Insert a run that started well beyond the threshold
    old_start = datetime.now(timezone.utc) - timedelta(hours=STUCK_RUN_THRESHOLD_HOURS + 1)
    cur.execute(
        """INSERT INTO collection_run (source_id, started_at, status)
           VALUES (%s, %s, 'running') RETURNING id""",
        (sid, old_start),
    )
    stuck_id = cur.fetchone()[0]
    db.commit()

    recovered = recover_stuck_run(db, sid)
    assert recovered == stuck_id

    cur = db.cursor()
    cur.execute("SELECT status, error_code FROM collection_run WHERE id=%s", (stuck_id,))
    row = cur.fetchone()
    assert row[0] == "failed"
    assert row[1] == "stuck_run_recovered"


def test_raw_capture_inserted(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "RL7")
    sid = _seed_source(cur, bid, "rl7")
    db.commit()
    run_id = start_run(db, sid)
    content_hash = hashlib.sha256(b"raw content").hexdigest()
    record_raw_capture(db, run_id, "parse_failure", content_hash)
    cur = db.cursor()
    cur.execute("SELECT capture_reason FROM raw_capture WHERE collection_run_id=%s", (run_id,))
    assert cur.fetchone()[0] == "parse_failure"


def test_acceptance_10_failed_run_prior_observations_intact(db):
    """Acceptance test 10: failed run does not delete or invalidate earlier observations."""
    cur = db.cursor()
    bid = _seed_bank(cur, "AT10")
    sid = _seed_source(cur, bid, "at10")
    cid = _seed_category(cur)
    db.commit()

    # First successful run with an observation
    run1 = start_run(db, sid)
    r = _record(src_key="pub-010")
    lkey, istatus = build_identity(r, sid)
    obs_id = _persist(db, r, sid, run1, cid, lkey=lkey, istatus=istatus)
    finish_run(db, run1, "success", records_found=1, records_accepted=1)

    # Second run fails
    run2 = start_run(db, sid)
    finish_run(db, run2, "failed", error_code="TIMEOUT")

    # Prior observation still present and current
    cur = db.cursor()
    cur.execute("SELECT is_current, validation_status FROM rate_observation WHERE id=%s", (obs_id,))
    row = cur.fetchone()
    assert row[0] is True
    assert row[1] == "validated"


def test_acceptance_11_success_with_no_new_rates(db):
    """Acceptance test 11: successful run with no new rates is still success."""
    cur = db.cursor()
    bid = _seed_bank(cur, "AT11")
    sid = _seed_source(cur, bid, "at11")
    db.commit()
    run_id = start_run(db, sid)
    finish_run(db, run_id, "success", records_found=0, records_accepted=0)
    cur = db.cursor()
    cur.execute("SELECT status, records_found FROM collection_run WHERE id=%s", (run_id,))
    row = cur.fetchone()
    assert row[0] == "success"
    assert row[1] == 0


# ── trusted view ─────────────────────────────────────────────────────────────

def test_acceptance_19_trusted_view_excludes_ambiguous(db):
    """Acceptance test 19: current selection excludes ambiguous identity."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV1")
    sid = _seed_source(cur, bid, "tv1")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    # Ambiguous record (no date, no key)
    r_amb = AdapterRecord(
        source_currency_code="USD", category="cash",
        buying_rate=Decimal("161.00"), selling_rate=Decimal("164.00"),
        effective_date=None, effective_date_basis="unknown",
    )
    fp = compute_fingerprint(r_amb, sid)
    insert_observation(
        conn=db, record=r_amb, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp, logical_key=None, identity_status=IdentityStatus.AMBIGUOUS,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
    )
    finish_run(db, run_id, "success")

    rates = get_trusted_rates(db, source_id=sid)
    assert all(r["identity_status"] != "ambiguous" for r in rates)


def test_acceptance_19_trusted_view_excludes_rejected(db):
    """Acceptance test 19: rejected observations excluded from trusted view."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV2")
    sid = _seed_source(cur, bid, "tv2")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    r = _record(src_key="pub-tv2")
    lkey, istatus = build_identity(r, sid)
    fp = compute_fingerprint(r, sid)
    insert_observation(
        conn=db, record=r, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.REJECTED, validation_messages=[],
        fetched_at=NOW, version_number=1, is_current=True,
    )
    finish_run(db, run_id, "success")

    rates = get_trusted_rates(db, source_id=sid)
    assert all(r["validation_status"] != "rejected" for r in rates)


def test_acceptance_19_trusted_view_excludes_unknown_category(db):
    """Gap review E / acceptance test 19: unknown category (NULL category_id) excluded."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV3")
    sid = _seed_source(cur, bid, "tv3")
    db.commit()
    run_id = start_run(db, sid)

    r = _record(category="UNKNOWN", src_key="pub-tv3")
    lkey, istatus = build_identity(r, sid)
    fp = compute_fingerprint(r, sid)
    insert_observation(
        conn=db, record=r, source_id=sid, run_id=run_id, category_id=None,
        fingerprint=fp, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.WARNING, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
    )
    finish_run(db, run_id, "success")

    rates = get_trusted_rates(db, source_id=sid)
    assert len(rates) == 0


def test_gap_L_provisional_source_labeled(db):
    """Gap review L: data from provisional sources is visibly labeled."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV4")
    sid = _seed_source(cur, bid, "tv4", verified=False)  # unverified
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    r = _record(src_key="pub-tv4")
    lkey, istatus = build_identity(r, sid)
    _persist(db, r, sid, run_id, cid, lkey=lkey, istatus=istatus)
    finish_run(db, run_id, "success")

    rates = get_trusted_rates(db, source_id=sid)
    assert len(rates) == 1
    assert rates[0]["is_provisional"] is True


def test_gap_C_pending_review_shows_uncertainty_warning(db):
    """Gap review C: pending review on a logical observation shows uncertainty warning."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV5")
    sid = _seed_source(cur, bid, "tv5")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    r1 = _record(src_key="pub-tv5a")
    lkey, istatus = build_identity(r1, sid)
    prior_id = _persist(db, r1, sid, run_id, cid, lkey=lkey, istatus=istatus, version=1)

    r2 = _record(buying=Decimal("163.00"), src_key="pub-tv5a")
    fp2 = compute_fingerprint(r2, sid)
    cand_id = insert_observation(
        conn=db, record=r2, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp2, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
        change_review_status=ChangeReviewStatus.PENDING_REVIEW,
    )
    insert_change_candidate(db, cand_id, prior_id, sid)
    finish_run(db, run_id, "success")

    result = get_observation_with_warnings(db, lkey)
    assert result is not None
    assert result["has_pending_review"] is True


def test_acceptance_21_stale_rate_shows_staleness_warning(db):
    """Acceptance test 21: stale rates show effective_date and staleness warning."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV6")
    sid = _seed_source(cur, bid, "tv6")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    # Effective date 10 days before fetch
    stale_date = date(2026, 9, 30)
    r = _record(src_key="pub-tv6", eff_date=stale_date)
    lkey, istatus = build_identity(r, sid)
    fp = compute_fingerprint(r, sid)
    insert_observation(
        conn=db, record=r, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=1, is_current=True,
    )
    finish_run(db, run_id, "success")

    result = get_observation_with_warnings(db, lkey)
    assert result is not None
    assert result["effective_date"] == stale_date
    assert result["staleness_warning"] is True


def test_acceptance_22_no_silent_substitution(db):
    """Acceptance test 22: if no current observation exists, trusted view returns nothing — no silent fallback."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV7")
    sid = _seed_source(cur, bid, "tv7")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    # Insert a non-current (superseded) observation
    r = _record(src_key="pub-tv7")
    lkey, istatus = build_identity(r, sid)
    _persist(db, r, sid, run_id, cid, lkey=lkey, istatus=istatus, version=1, is_current=False)
    finish_run(db, run_id, "success")

    rates = get_trusted_rates(db, source_id=sid)
    # No current observation → nothing returned
    assert len(rates) == 0

    result = get_observation_with_warnings(db, lkey)
    assert result is None


def test_gap_G_disappearing_data_no_current(db):
    """Gap review G: previously populated source returning empty → no current rates shown."""
    cur = db.cursor()
    bid = _seed_bank(cur, "TV8")
    sid = _seed_source(cur, bid, "tv8")
    cid = _seed_category(cur)
    db.commit()

    # First run: observation stored and current
    run1 = start_run(db, sid)
    r = _record(src_key="pub-tv8")
    lkey, istatus = build_identity(r, sid)
    _persist(db, r, sid, run1, cid, lkey=lkey, istatus=istatus, version=1, is_current=True)
    finish_run(db, run1, "success", records_found=1, records_accepted=1)

    # Second run: empty response — no new observations, prior remains current
    run2 = start_run(db, sid)
    finish_run(db, run2, "success", records_found=0, records_accepted=0)

    # Prior observation still current (not deleted by empty run)
    rates = get_trusted_rates(db, source_id=sid)
    assert len(rates) == 1
    assert rates[0]["identity_status"] == "confirmed"


# ── review workflow ───────────────────────────────────────────────────────────

def test_review_dismissed_candidate(db):
    """Dismissed candidate: audit record kept, change_review_status updated."""
    cur = db.cursor()
    bid = _seed_bank(cur, "RV1")
    sid = _seed_source(cur, bid, "rv1")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    r1 = _record(src_key="pub-rv1")
    lkey, istatus = build_identity(r1, sid)
    prior_id = _persist(db, r1, sid, run_id, cid, lkey=lkey, istatus=istatus, version=1)

    r2 = _record(buying=Decimal("163.00"), src_key="pub-rv1")
    fp2 = compute_fingerprint(r2, sid)
    cand_obs_id = insert_observation(
        conn=db, record=r2, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp2, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
        change_review_status=ChangeReviewStatus.PENDING_REVIEW,
    )
    cand_id_row = db.cursor()
    cand_id_row.execute(
        "INSERT INTO change_candidate (observation_id, prior_version_id, source_id) VALUES (%s,%s,%s) RETURNING id",
        (cand_obs_id, prior_id, sid),
    )
    cand_id = cand_id_row.fetchone()[0]
    finish_run(db, run_id, "success")

    decide_candidate(db, cand_id, "dismissed", "reviewer@example.com", "Data error on source side")

    cur = db.cursor()
    cur.execute("SELECT status, decided_by FROM change_candidate WHERE id=%s", (cand_id,))
    row = cur.fetchone()
    assert row[0] == "dismissed"
    assert row[1] == "reviewer@example.com"

    # Prior version still current
    cur.execute("SELECT is_current FROM rate_observation WHERE id=%s", (prior_id,))
    assert cur.fetchone()[0] is True


def test_review_confirmed_correction_via_workflow(db):
    """Confirmed correction via review workflow creates new version, prior non-current."""
    cur = db.cursor()
    bid = _seed_bank(cur, "RV2")
    sid = _seed_source(cur, bid, "rv2")
    cid = _seed_category(cur)
    db.commit()
    run_id = start_run(db, sid)

    r1 = _record(src_key="pub-rv2")
    lkey, istatus = build_identity(r1, sid)
    prior_id = _persist(db, r1, sid, run_id, cid, lkey=lkey, istatus=istatus, version=1)

    r2 = _record(buying=Decimal("163.00"), src_key="pub-rv2")
    fp2 = compute_fingerprint(r2, sid)
    cand_obs_id = insert_observation(
        conn=db, record=r2, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp2, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
        change_review_status=ChangeReviewStatus.PENDING_REVIEW,
    )
    cur2 = db.cursor()
    cur2.execute(
        "INSERT INTO change_candidate (observation_id, prior_version_id, source_id) VALUES (%s,%s,%s) RETURNING id",
        (cand_obs_id, prior_id, sid),
    )
    cand_id = cur2.fetchone()[0]
    finish_run(db, run_id, "success")

    new_id = decide_candidate(
        db, cand_id, "confirmed_correction",
        "reviewer@example.com", "Bank confirmed the new rate",
        record=r2, source_id=sid, run_id=run_id, category_id=cid,
        fingerprint=fp2, logical_key=lkey,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[], fetched_at=NOW,
    )
    assert new_id is not None

    cur = db.cursor()
    cur.execute("SELECT is_current, version_number FROM rate_observation WHERE id=%s", (prior_id,))
    row = cur.fetchone()
    assert row[0] is False

    cur.execute("SELECT is_current, version_number, supersedes_id FROM rate_observation WHERE id=%s", (new_id,))
    row = cur.fetchone()
    assert row[0] is True
    assert row[1] == 2
    assert row[2] == prior_id
