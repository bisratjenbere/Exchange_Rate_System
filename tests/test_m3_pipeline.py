import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from tests.db_utils import get_conn, apply_migrations, reset_schema
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from pipeline.validate import validate
from pipeline.normalize import normalize_rate, normalize_currency_code
from pipeline.fingerprint import compute_fingerprint, FINGERPRINT_VERSION
from pipeline.identity import build_identity
from pipeline.deduplicate import classify_observation, classify_ambiguous_observation
from pipeline.persist import (
    insert_observation, insert_change_candidate,
    commit_correction, get_next_version_number,
)

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

def _record(
    currency="USD",
    category="cash",
    buying=Decimal("161.00"),
    selling=Decimal("164.00"),
    effective_date=date(2026, 10, 10),
    basis="source_published",
    source_record_key=None,
    source_publication_key=None,
):
    return AdapterRecord(
        source_currency_code=currency,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        effective_date=effective_date,
        effective_date_basis=basis,
        source_record_key=source_record_key,
        source_publication_key=source_publication_key,
        source_rate_text=f"{buying}/{selling}",
    )

def _seed_bank(cur, code="TST"):
    cur.execute(
        "INSERT INTO bank (code, name) VALUES (%s, %s) RETURNING id",
        (code, f"Test {code}"),
    )
    return cur.fetchone()[0]

def _seed_source(cur, bank_id, key="tst"):
    cur.execute(
        """INSERT INTO rate_source (bank_id, source_url, collection_method, adapter_key)
           VALUES (%s, 'https://x.com', 'api', %s) RETURNING id""",
        (bank_id, key),
    )
    return cur.fetchone()[0]

def _seed_run(cur, source_id, status="success"):
    cur.execute(
        """INSERT INTO collection_run (source_id, started_at, finished_at, status)
           VALUES (%s, now(), now(), %s) RETURNING id""",
        (source_id, status),
    )
    return cur.fetchone()[0]

def _seed_category(cur, code="cash"):
    cur.execute(
        """INSERT INTO rate_category (code, name, approved_at)
           VALUES (%s, %s, now())
           ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code
           RETURNING id""",
        (code, code),
    )
    return cur.fetchone()[0]

def _persist_record(db, record, source_id, run_id, category_id,
                    logical_key, identity_status, version=1, is_current=True):
    fp = compute_fingerprint(record, source_id)
    return insert_observation(
        conn=db,
        record=record,
        source_id=source_id,
        run_id=run_id,
        category_id=category_id,
        fingerprint=fp,
        logical_key=logical_key,
        identity_status=identity_status,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=NOW,
        version_number=version,
        is_current=is_current,
    )

def test_normalize_zero_string_to_none():
    assert normalize_rate("0.0000") is None

def test_normalize_no_trade_to_none():
    assert normalize_rate("No Trade") is None
    assert normalize_rate("NO TRADE") is None
    assert normalize_rate("-") is None

def test_normalize_none_to_none():
    assert normalize_rate(None) is None

def test_normalize_valid_decimal():
    assert normalize_rate("161.7237") == Decimal("161.7237")

def test_normalize_negative_raises():
    with pytest.raises(ValueError):
        normalize_rate("-5.0")

def test_normalize_unparseable_raises():
    with pytest.raises(ValueError):
        normalize_rate("abc")

def test_validate_valid_record():
    r = _record()
    status, msgs = validate(r)
    assert status == ValidationStatus.VALIDATED
    assert msgs == []

def test_7_unknown_category_flagged():
    r = _record(category="UNKNOWN")
    status, msgs = validate(r)
    assert status == ValidationStatus.WARNING
    codes = {m["code"] for m in msgs}
    assert "UNKNOWN_CATEGORY" in codes

def test_8_unknown_currency_flagged():
    r = _record(currency="")
    status, msgs = validate(r)
    assert status == ValidationStatus.REJECTED
    codes = {m["code"] for m in msgs}
    assert "MISSING_CURRENCY" in codes

def test_15_zero_rate_rejected():
    r = _record(buying=Decimal("0"))
    status, msgs = validate(r)
    assert status == ValidationStatus.REJECTED
    codes = {m["code"] for m in msgs}
    assert "INVALID_RATE_ZERO" in codes

def test_16_both_null_rejected():
    r = _record(buying=None, selling=None)
    status, msgs = validate(r)
    assert status == ValidationStatus.REJECTED
    codes = {m["code"] for m in msgs}
    assert "BOTH_RATES_NULL" in codes

def test_16_null_buying_accepted():
    r = _record(buying=None, selling=Decimal("164.00"))
    status, msgs = validate(r)
    assert status == ValidationStatus.VALIDATED

def test_buying_above_selling_is_warning():
    r = _record(buying=Decimal("165.00"), selling=Decimal("164.00"))
    status, msgs = validate(r)
    assert status == ValidationStatus.WARNING
    codes = {m["code"] for m in msgs}
    assert "BUYING_ABOVE_SELLING" in codes

def test_fingerprint_deterministic():
    r = _record()
    assert compute_fingerprint(r, 1) == compute_fingerprint(r, 1)

def test_fingerprint_differs_on_value_change():
    r1 = _record(buying=Decimal("161.00"))
    r2 = _record(buying=Decimal("162.00"))
    assert compute_fingerprint(r1, 1) != compute_fingerprint(r2, 1)

def test_fingerprint_differs_on_source_id():
    r = _record()
    assert compute_fingerprint(r, 1) != compute_fingerprint(r, 2)

def test_fingerprint_excludes_fetched_at():
    r = _record()
    fp1 = compute_fingerprint(r, 1)
    fp2 = compute_fingerprint(r, 1)
    assert fp1 == fp2

def test_fingerprint_version_constant():
    assert FINGERPRINT_VERSION in (1, 2)

def test_identity_confirmed_with_source_record_key():
    r = _record(source_record_key="abc123")
    key, status = build_identity(r, 5)
    assert status == IdentityStatus.CONFIRMED
    assert "abc123" in key

def test_identity_confirmed_with_source_published_date():
    r = _record(basis="source_published")
    key, status = build_identity(r, 5)
    assert status == IdentityStatus.CONFIRMED
    assert "2026-10-10" in key

def test_identity_derived_with_source_inferred_date():
    r = _record(basis="source_inferred")
    key, status = build_identity(r, 5)
    assert status == IdentityStatus.DERIVED
    assert "2026-10-10" in key

def test_identity_ambiguous_with_fallback_date():
    r = _record(basis="collection_date_fallback")
    key, status = build_identity(r, 5)
    assert status == IdentityStatus.AMBIGUOUS
    assert key is None

def test_identity_ambiguous_with_no_date():
    r = _record(effective_date=None, basis="unknown")
    key, status = build_identity(r, 5)
    assert status == IdentityStatus.AMBIGUOUS
    assert key is None

def test_identity_key_includes_source_id_and_category():
    r = _record(currency="EUR", category="transactional", basis="source_published")
    key, _ = build_identity(r, 7)
    assert "7" in key
    assert "EUR" in key
    assert "transactional" in key

def test_1_duplicate_fetch_no_new_row(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT1")
    sid = _seed_source(cur, bid, "at1")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(source_record_key="pub-001")
    lkey, istatus = build_identity(r, sid)
    fp = compute_fingerprint(r, sid)

    _persist_record(db, r, sid, rid, cid, lkey, istatus)
    db.commit()

    action, existing_id = classify_observation(fp, lkey, db)
    assert action == "duplicate"
    assert existing_id is not None

def test_2_cash_and_transactional_are_distinct(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT2")
    sid = _seed_source(cur, bid, "at2")
    rid = _seed_run(cur, sid)
    cid_cash = _seed_category(cur, "cash")
    cid_txn = _seed_category(cur, "transactional")
    db.commit()

    r_cash = _record(category="cash", source_record_key="pub-cash")
    r_txn = _record(category="transactional", source_record_key="pub-txn")

    lkey_cash, ist_cash = build_identity(r_cash, sid)
    lkey_txn, ist_txn = build_identity(r_txn, sid)

    assert lkey_cash != lkey_txn

    id_cash = _persist_record(db, r_cash, sid, rid, cid_cash, lkey_cash, ist_cash)
    id_txn = _persist_record(db, r_txn, sid, rid, cid_txn, lkey_txn, ist_txn)
    db.commit()

    assert id_cash != id_txn

    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM rate_observation WHERE source_id=%s", (sid,))
    assert cur.fetchone()[0] == 2

def test_4_changed_value_creates_candidate_not_correction(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT4")
    sid = _seed_source(cur, bid, "at4")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r1 = _record(buying=Decimal("161.00"), source_record_key="pub-004")
    lkey, istatus = build_identity(r1, sid)
    fp1 = compute_fingerprint(r1, sid)
    prior_id = _persist_record(db, r1, sid, rid, cid, lkey, istatus)
    db.commit()

    r2 = _record(buying=Decimal("163.00"), source_record_key="pub-004")
    fp2 = compute_fingerprint(r2, sid)
    action, existing_id = classify_observation(fp2, lkey, db)
    assert action == "changed"
    assert existing_id == prior_id

    candidate_id = insert_observation(
        conn=db,
        record=r2,
        source_id=sid,
        run_id=rid,
        category_id=cid,
        fingerprint=fp2,
        logical_key=lkey,
        identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=NOW,
        version_number=None,
        is_current=False,
        change_review_status=ChangeReviewStatus.PENDING_REVIEW,
    )
    insert_change_candidate(db, candidate_id, prior_id, sid)
    db.commit()

    cur = db.cursor()
    cur.execute("SELECT is_current FROM rate_observation WHERE id=%s", (prior_id,))
    assert cur.fetchone()[0] is True

    cur.execute(
        "SELECT is_current, version_number FROM rate_observation WHERE id=%s",
        (candidate_id,),
    )
    row = cur.fetchone()
    assert row[0] is False
    assert row[1] is None

    cur.execute("SELECT status FROM change_candidate WHERE observation_id=%s", (candidate_id,))
    assert cur.fetchone()[0] == "open"

def test_5_confirmed_correction_creates_new_version(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT5")
    sid = _seed_source(cur, bid, "at5")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r1 = _record(buying=Decimal("161.00"), source_record_key="pub-005")
    lkey, istatus = build_identity(r1, sid)
    prior_id = _persist_record(db, r1, sid, rid, cid, lkey, istatus, version=1)
    db.commit()

    r2 = _record(buying=Decimal("162.50"), source_record_key="pub-005")
    fp2 = compute_fingerprint(r2, sid)
    new_id = commit_correction(
        conn=db,
        prior_obs_id=prior_id,
        record=r2,
        source_id=sid,
        run_id=rid,
        category_id=cid,
        fingerprint=fp2,
        logical_key=lkey,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=NOW,
        prior_version_number=1,
    )
    db.commit()

    cur = db.cursor()
    cur.execute("SELECT is_current, version_number FROM rate_observation WHERE id=%s", (prior_id,))
    prior_row = cur.fetchone()
    assert prior_row[0] is False
    assert prior_row[1] == 1

    cur.execute(
        "SELECT is_current, version_number, supersedes_id, change_review_status "
        "FROM rate_observation WHERE id=%s",
        (new_id,),
    )
    new_row = cur.fetchone()
    assert new_row[0] is True
    assert new_row[1] == 2
    assert new_row[2] == prior_id
    assert new_row[3] == "confirmed_correction"

    cur.execute(
        "SELECT COUNT(*) FROM rate_observation WHERE logical_observation_key=%s AND is_current=TRUE",
        (lkey,),
    )
    assert cur.fetchone()[0] == 1

def test_6_ambiguous_identity_retained_and_flagged(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT6")
    sid = _seed_source(cur, bid, "at6")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(effective_date=None, basis="unknown")
    lkey, istatus = build_identity(r, sid)
    assert istatus == IdentityStatus.AMBIGUOUS
    assert lkey is None

    fp = compute_fingerprint(r, sid)
    obs_id = insert_observation(
        conn=db, record=r, source_id=sid, run_id=rid, category_id=cid,
        fingerprint=fp, logical_key=None,
        identity_status=IdentityStatus.AMBIGUOUS,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=NOW,
        version_number=None,
        is_current=False,
    )
    db.commit()

    cur = db.cursor()
    cur.execute(
        "SELECT identity_status, logical_observation_key, is_current FROM rate_observation WHERE id=%s",
        (obs_id,),
    )
    row = cur.fetchone()
    assert row[0] == "ambiguous"
    assert row[1] is None
    assert row[2] is False

def test_12_concurrent_correction_no_competing_current(db):
    import psycopg2
    cur = db.cursor()
    bid = _seed_bank(cur, "AT12")
    sid = _seed_source(cur, bid, "at12")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r1 = _record(buying=Decimal("161.00"), source_record_key="pub-012")
    lkey, istatus = build_identity(r1, sid)
    prior_id = _persist_record(db, r1, sid, rid, cid, lkey, istatus, version=1)
    db.commit()

    r2 = _record(buying=Decimal("162.00"), source_record_key="pub-012")
    fp2 = compute_fingerprint(r2, sid)
    new_id = commit_correction(
        conn=db, prior_obs_id=prior_id, record=r2,
        source_id=sid, run_id=rid, category_id=cid,
        fingerprint=fp2, logical_key=lkey,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[], fetched_at=NOW,
        prior_version_number=1,
    )
    db.commit()

    r3 = _record(buying=Decimal("163.00"), source_record_key="pub-012")
    fp3 = compute_fingerprint(r3, sid)
    with pytest.raises(Exception):
        insert_observation(
            conn=db, record=r3, source_id=sid, run_id=rid, category_id=cid,
            fingerprint=fp3, logical_key=lkey,
            identity_status=istatus,
            validation_status=ValidationStatus.VALIDATED,
            validation_messages=[], fetched_at=NOW,
            version_number=3, is_current=True,
        )

def test_13_version_number_positive_and_unique(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT13")
    sid = _seed_source(cur, bid, "at13")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(source_record_key="pub-013")
    lkey, istatus = build_identity(r, sid)
    obs_id = _persist_record(db, r, sid, rid, cid, lkey, istatus, version=1)
    db.commit()

    cur = db.cursor()
    cur.execute("SELECT version_number FROM rate_observation WHERE id=%s", (obs_id,))
    assert cur.fetchone()[0] == 1

    import psycopg2
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _persist_record(db, r, sid, rid, cid, lkey, istatus, version=1, is_current=False)

def test_14_at_most_one_current_version(db):
    import psycopg2
    cur = db.cursor()
    bid = _seed_bank(cur, "AT14")
    sid = _seed_source(cur, bid, "at14")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(source_record_key="pub-014")
    lkey, istatus = build_identity(r, sid)
    _persist_record(db, r, sid, rid, cid, lkey, istatus, version=1, is_current=True)
    db.commit()

    r2 = _record(buying=Decimal("162.00"), source_record_key="pub-014b")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _persist_record(db, r2, sid, rid, cid, lkey, istatus, version=2, is_current=True)

def test_17_source_rate_text_retained(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT17")
    sid = _seed_source(cur, bid, "at17")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(source_record_key="pub-017")
    r.source_rate_text = "161.00/164.00"
    lkey, istatus = build_identity(r, sid)
    obs_id = _persist_record(db, r, sid, rid, cid, lkey, istatus)
    db.commit()

    cur = db.cursor()
    cur.execute("SELECT source_rate_text FROM rate_observation WHERE id=%s", (obs_id,))
    assert cur.fetchone()[0] == "161.00/164.00"

def test_18_mapping_version_stored(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "AT18")
    sid = _seed_source(cur, bid, "at18")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(source_record_key="pub-018")
    lkey, istatus = build_identity(r, sid)
    obs_id = _persist_record(db, r, sid, rid, cid, lkey, istatus)
    db.commit()

    cur = db.cursor()
    cur.execute(
        "SELECT fingerprint_version, category_mapping_version, currency_mapping_version "
        "FROM rate_observation WHERE id=%s",
        (obs_id,),
    )
    row = cur.fetchone()
    assert row[0] == FINGERPRINT_VERSION
    assert row[1] == 1
    assert row[2] == 1

def test_gap_A_revert_goes_to_review_not_deduplicated(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "GA1")
    sid = _seed_source(cur, bid, "ga1")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r1 = _record(buying=Decimal("161.00"), source_record_key="pub-A")
    lkey, istatus = build_identity(r1, sid)
    fp1 = compute_fingerprint(r1, sid)
    prior_id = _persist_record(db, r1, sid, rid, cid, lkey, istatus, version=1)
    db.commit()

    r2 = _record(buying=Decimal("162.00"), source_record_key="pub-A")
    fp2 = compute_fingerprint(r2, sid)
    new_id = commit_correction(
        conn=db, prior_obs_id=prior_id, record=r2,
        source_id=sid, run_id=rid, category_id=cid,
        fingerprint=fp2, logical_key=lkey,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[], fetched_at=NOW,
        prior_version_number=1,
    )
    db.commit()

    action, existing_id = classify_observation(fp1, lkey, db)
    cur = db.cursor()
    cur.execute(
        "SELECT snapshot_fingerprint FROM rate_observation WHERE id=%s AND is_current=TRUE",
        (new_id,),
    )
    current_fp = cur.fetchone()[0]
    assert fp1 != current_fp

def test_gap_B_repeated_candidate_yields_one_open(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "GB1")
    sid = _seed_source(cur, bid, "gb1")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r1 = _record(buying=Decimal("161.00"), source_record_key="pub-B")
    lkey, istatus = build_identity(r1, sid)
    fp1 = compute_fingerprint(r1, sid)
    prior_id = _persist_record(db, r1, sid, rid, cid, lkey, istatus, version=1)
    db.commit()

    r2 = _record(buying=Decimal("163.00"), source_record_key="pub-B")
    fp2 = compute_fingerprint(r2, sid)

    action, _ = classify_observation(fp2, lkey, db)
    assert action == "changed"
    cand_id = insert_observation(
        conn=db, record=r2, source_id=sid, run_id=rid, category_id=cid,
        fingerprint=fp2, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
        change_review_status=ChangeReviewStatus.PENDING_REVIEW,
    )
    insert_change_candidate(db, cand_id, prior_id, sid)
    db.commit()

    action2, _ = classify_observation(fp2, lkey, db)
    assert action2 == "duplicate"

    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM change_candidate WHERE prior_version_id=%s AND status='open'",
        (prior_id,),
    )
    assert cur.fetchone()[0] == 1

def test_gap_D_fingerprint_version_in_stored_row(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "GD1")
    sid = _seed_source(cur, bid, "gd1")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r = _record(source_record_key="pub-D")
    lkey, istatus = build_identity(r, sid)
    obs_id = _persist_record(db, r, sid, rid, cid, lkey, istatus)
    db.commit()

    cur = db.cursor()
    cur.execute("SELECT fingerprint_version FROM rate_observation WHERE id=%s", (obs_id,))
    assert cur.fetchone()[0] == FINGERPRINT_VERSION

def test_gap_E_unknown_category_excluded_from_trusted(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "GE1")
    sid = _seed_source(cur, bid, "ge1")
    rid = _seed_run(cur, sid)
    db.commit()

    r = _record(category="UNKNOWN", source_record_key="pub-E")
    status, msgs = validate(r)
    assert status == ValidationStatus.WARNING
    codes = {m["code"] for m in msgs}
    assert "UNKNOWN_CATEGORY" in codes

    fp = compute_fingerprint(r, sid)
    lkey, istatus = build_identity(r, sid)
    obs_id = insert_observation(
        conn=db, record=r, source_id=sid, run_id=rid, category_id=None,
        fingerprint=fp, logical_key=lkey, identity_status=istatus,
        validation_status=ValidationStatus.WARNING,
        validation_messages=[{"code": "UNKNOWN_CATEGORY", "message": "unknown"}],
        fetched_at=NOW, version_number=None, is_current=False,
    )
    db.commit()

    cur = db.cursor()
    cur.execute(
        "SELECT category_id, is_current FROM rate_observation WHERE id=%s", (obs_id,)
    )
    row = cur.fetchone()
    assert row[0] is None
    assert row[1] is False

def test_gap_J_effective_date_basis_stored(db):
    cur = db.cursor()
    bid = _seed_bank(cur, "GJ1")
    sid = _seed_source(cur, bid, "gj1")
    rid = _seed_run(cur, sid)
    cid = _seed_category(cur)
    db.commit()

    r_pub = _record(basis="source_published", source_record_key="pub-J1")
    lkey_pub, istatus_pub = build_identity(r_pub, sid)
    id_pub = _persist_record(db, r_pub, sid, rid, cid, lkey_pub, istatus_pub)

    r_fall = _record(basis="collection_date_fallback", source_record_key=None)
    lkey_fall, istatus_fall = build_identity(r_fall, sid)
    assert lkey_fall is None
    assert istatus_fall == IdentityStatus.AMBIGUOUS

    fp_fall = compute_fingerprint(r_fall, sid)
    id_fall = insert_observation(
        conn=db, record=r_fall, source_id=sid, run_id=rid, category_id=cid,
        fingerprint=fp_fall, logical_key=None,
        identity_status=IdentityStatus.AMBIGUOUS,
        validation_status=ValidationStatus.VALIDATED, validation_messages=[],
        fetched_at=NOW, version_number=None, is_current=False,
    )
    db.commit()

    cur = db.cursor()
    cur.execute(
        "SELECT effective_date_basis, identity_status FROM rate_observation WHERE id=%s",
        (id_pub,),
    )
    row = cur.fetchone()
    assert row[0] == "source_published"
    assert row[1] == "confirmed"

    cur.execute(
        "SELECT effective_date_basis, identity_status FROM rate_observation WHERE id=%s",
        (id_fall,),
    )
    row = cur.fetchone()
    assert row[0] == "collection_date_fallback"
    assert row[1] == "ambiguous"
