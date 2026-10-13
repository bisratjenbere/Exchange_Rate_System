"""
M2 constraint tests — run against a real PostgreSQL database.
Each test is named after the rule it enforces.
All tests require the schema to be applied first (apply_migrations fixture).
"""
import pytest
import psycopg2
from tests.db_utils import get_conn, apply_migrations, reset_schema


@pytest.fixture(scope="module")
def db():
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def rollback(db):
    """Roll back after every test for isolation."""
    yield
    db.rollback()


# ── seed helpers ────────────────────────────────────────────────────────────

def seed_bank(cur, code="TST", authority="official"):
    cur.execute(
        "INSERT INTO bank (code, name, source_authority) VALUES (%s, %s, %s) RETURNING id",
        (code, f"Test Bank {code}", authority)
    )
    return cur.fetchone()[0]


def seed_source(cur, bank_id, adapter_key="tst_api"):
    cur.execute(
        """INSERT INTO rate_source (bank_id, source_url, collection_method, adapter_key)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (bank_id, "https://example.com/api", "api", adapter_key)
    )
    return cur.fetchone()[0]


def seed_category(cur, code="cash"):
    cur.execute(
        """INSERT INTO rate_category (code, name, approved_at)
           VALUES (%s, %s, now()) ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code
           RETURNING id""",
        (code, code.replace("_", " ").title())
    )
    return cur.fetchone()[0]


def seed_run(cur, source_id, status="success"):
    cur.execute(
        """INSERT INTO collection_run (source_id, started_at, finished_at, status)
           VALUES (%s, now(), now(), %s) RETURNING id""",
        (source_id, status)
    )
    return cur.fetchone()[0]


def seed_obs(cur, source_id, run_id, category_id,
             buying=100.0, selling=102.0,
             currency="USD", version=1, is_current=False,
             identity_status="confirmed", lkey=None):
    cur.execute(
        """INSERT INTO rate_observation (
               source_id, collection_run_id, category_id,
               source_currency_code, buying_rate, selling_rate,
               effective_date, effective_date_basis,
               fetched_at, snapshot_fingerprint, fingerprint_version,
               version_number, is_current, identity_status,
               validation_status, change_review_status,
               logical_observation_key
           ) VALUES (
               %s, %s, %s, %s, %s, %s,
               '2026-10-10', 'source_published',
               now(), md5(random()::text), 1,
               %s, %s, %s,
               'validated', 'not_required',
               %s
           ) RETURNING id""",
        (source_id, run_id, category_id,
         currency, buying, selling,
         version, is_current, identity_status,
         lkey or f"{source_id}:{currency}:cash:2026-10-10")
    )
    return cur.fetchone()[0]


# ── rate value checks ────────────────────────────────────────────────────────

def test_buying_rate_must_be_positive(db):
    """Acceptance test 15 partial: no silent coercion — negative buying rejected."""
    cur = db.cursor()
    bid = seed_bank(cur, "B01")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        seed_obs(cur, sid, rid, cid, buying=-1.0)


def test_selling_rate_must_be_positive(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B02")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        seed_obs(cur, sid, rid, cid, selling=-1.0)


def test_zero_buying_rate_rejected(db):
    """Zero is not a valid rate — must be NULL for missing side."""
    cur = db.cursor()
    bid = seed_bank(cur, "B03")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        seed_obs(cur, sid, rid, cid, buying=0.0)


def test_both_sides_null_rejected(db):
    """Acceptance test 16: at least one side must be non-NULL."""
    cur = db.cursor()
    bid = seed_bank(cur, "B04")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO rate_observation (
                   source_id, collection_run_id, category_id,
                   source_currency_code, buying_rate, selling_rate,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   validation_status, change_review_status, identity_status
               ) VALUES (%s,%s,%s,'USD',NULL,NULL,'2026-10-10','source_published',
                         now(),md5(random()::text),1,'validated','not_required','confirmed')""",
            (sid, rid, cid)
        )


def test_null_buying_with_valid_selling_accepted(db):
    """Acceptance test 16: missing side is NULL, not zero — NULL buying is valid."""
    cur = db.cursor()
    bid = seed_bank(cur, "B05")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    cur.execute(
        """INSERT INTO rate_observation (
               source_id, collection_run_id, category_id,
               source_currency_code, buying_rate, selling_rate,
               effective_date, effective_date_basis,
               fetched_at, snapshot_fingerprint, fingerprint_version,
               validation_status, change_review_status, identity_status
           ) VALUES (%s,%s,%s,'USD',NULL,102.0,'2026-10-10','source_published',
                     now(),md5(random()::text),1,'validated','not_required','confirmed')""",
        (sid, rid, cid)
    )
    db.commit()


# ── version integrity ────────────────────────────────────────────────────────

def test_version_number_must_be_positive(db):
    """Acceptance test 13: version_number > 0 for committed versions."""
    cur = db.cursor()
    bid = seed_bank(cur, "B06")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        seed_obs(cur, sid, rid, cid, version=0)


def test_version_number_null_allowed_for_candidates(db):
    """Gap review §2: candidates have NULL version_number."""
    cur = db.cursor()
    bid = seed_bank(cur, "B07")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    cur.execute(
        """INSERT INTO rate_observation (
               source_id, collection_run_id, category_id,
               source_currency_code, buying_rate, selling_rate,
               effective_date, effective_date_basis,
               fetched_at, snapshot_fingerprint, fingerprint_version,
               version_number, is_current, identity_status,
               validation_status, change_review_status
           ) VALUES (%s,%s,%s,'USD',100.0,102.0,'2026-10-10','source_published',
                     now(),md5(random()::text),1,
                     NULL,false,'ambiguous','warning','pending_review')""",
        (sid, rid, cid)
    )
    db.commit()


def test_supersedes_id_cannot_self_reference(db):
    """Acceptance test 13: no cycles — supersedes_id != id."""
    cur = db.cursor()
    bid = seed_bank(cur, "B08")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    oid = seed_obs(cur, sid, rid, cid)
    db.commit()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "UPDATE rate_observation SET supersedes_id = id WHERE id = %s", (oid,)
        )


def test_unique_version_per_logical_key(db):
    """Acceptance test 13: unique (logical_observation_key, version_number)."""
    cur = db.cursor()
    bid = seed_bank(cur, "B09")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    lkey = f"{sid}:USD:cash:2026-10-10:unique_v"
    seed_obs(cur, sid, rid, cid, version=1, lkey=lkey)
    db.commit()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        seed_obs(cur, sid, rid, cid, version=1, lkey=lkey)


# ── one current version per logical observation ──────────────────────────────

def test_at_most_one_current_version_per_logical_key(db):
    """Acceptance test 14: at most one is_current=true per logical_observation_key."""
    cur = db.cursor()
    bid = seed_bank(cur, "B10")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    lkey = f"{sid}:USD:cash:2026-10-10:current_test"
    seed_obs(cur, sid, rid, cid, version=1, is_current=True, lkey=lkey)
    db.commit()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        seed_obs(cur, sid, rid, cid, version=2, is_current=True, lkey=lkey)


def test_multiple_non_current_versions_allowed(db):
    """Multiple non-current versions for same logical key are allowed."""
    cur = db.cursor()
    bid = seed_bank(cur, "B11")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    lkey = f"{sid}:USD:cash:2026-10-10:multi_noncurrent"
    seed_obs(cur, sid, rid, cid, version=1, is_current=False, lkey=lkey)
    seed_obs(cur, sid, rid, cid, version=2, is_current=False, lkey=lkey)
    db.commit()


# ── run overlap guard ────────────────────────────────────────────────────────

def test_one_running_run_per_source(db):
    """Gap review §7: cannot have two running runs for the same source."""
    cur = db.cursor()
    bid = seed_bank(cur, "B12")
    sid = seed_source(cur, bid)
    seed_run(cur, sid, status="running")
    db.commit()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        seed_run(cur, sid, status="running")


def test_second_run_allowed_after_first_completes(db):
    """A new run is allowed once the previous run is no longer running."""
    cur = db.cursor()
    bid = seed_bank(cur, "B13")
    sid = seed_source(cur, bid)
    rid = seed_run(cur, sid, status="running")
    db.commit()
    cur.execute("UPDATE collection_run SET status='success' WHERE id=%s", (rid,))
    db.commit()
    seed_run(cur, sid, status="running")
    db.commit()


# ── status enum checks ───────────────────────────────────────────────────────

def test_invalid_run_status_rejected(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B14")
    sid = seed_source(cur, bid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO collection_run (source_id, started_at, status)
               VALUES (%s, now(), 'invalid_status')""", (sid,)
        )


def test_invalid_validation_status_rejected(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B15")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO rate_observation (
                   source_id, collection_run_id, category_id,
                   source_currency_code, buying_rate, selling_rate,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   validation_status, change_review_status, identity_status
               ) VALUES (%s,%s,%s,'USD',100.0,102.0,'2026-10-10','source_published',
                         now(),md5(random()::text),1,
                         'bad_status','not_required','confirmed')""",
            (sid, rid, cid)
        )


def test_invalid_identity_status_rejected(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B16")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO rate_observation (
                   source_id, collection_run_id, category_id,
                   source_currency_code, buying_rate, selling_rate,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   validation_status, change_review_status, identity_status
               ) VALUES (%s,%s,%s,'USD',100.0,102.0,'2026-10-10','source_published',
                         now(),md5(random()::text),1,
                         'validated','not_required','not_a_status')""",
            (sid, rid, cid)
        )


def test_invalid_effective_date_basis_rejected(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B17")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO rate_observation (
                   source_id, collection_run_id, category_id,
                   source_currency_code, buying_rate, selling_rate,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   validation_status, change_review_status, identity_status
               ) VALUES (%s,%s,%s,'USD',100.0,102.0,'2026-10-10','guessed',
                         now(),md5(random()::text),1,
                         'validated','not_required','confirmed')""",
            (sid, rid, cid)
        )


# ── foreign key integrity ────────────────────────────────────────────────────

def test_observation_requires_valid_source(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B18")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        seed_obs(cur, source_id=99999, run_id=rid, category_id=cid)


def test_observation_requires_valid_run(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B19")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        seed_obs(cur, source_id=sid, run_id=99999, category_id=cid)


def test_source_requires_valid_bank(db):
    cur = db.cursor()
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute(
            """INSERT INTO rate_source (bank_id, source_url, collection_method, adapter_key)
               VALUES (99999, 'https://x.com', 'api', 'x_api')"""
        )


# ── collection run counters ──────────────────────────────────────────────────

def test_run_counters_default_to_zero(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B20")
    sid = seed_source(cur, bid)
    rid = seed_run(cur, sid)
    db.commit()
    cur.execute(
        "SELECT records_found, records_accepted, records_flagged FROM collection_run WHERE id=%s",
        (rid,)
    )
    found, accepted, flagged = cur.fetchone()
    assert found == 0
    assert accepted == 0
    assert flagged == 0


def test_run_counters_cannot_be_negative(db):
    cur = db.cursor()
    bid = seed_bank(cur, "B21")
    sid = seed_source(cur, bid)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO collection_run (source_id, started_at, status, records_found)
               VALUES (%s, now(), 'success', -1)""", (sid,)
        )


# ── source authority ─────────────────────────────────────────────────────────

def test_invalid_source_authority_rejected(db):
    cur = db.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """INSERT INTO bank (code, name, source_authority)
               VALUES ('BAD', 'Bad Bank', 'unknown_authority')"""
        )


# ── reinterpretation link ────────────────────────────────────────────────────

def test_reinterpretation_cannot_self_reference(db):
    """ADR-005 / gap review §3: reinterpretation_of_id != id."""
    cur = db.cursor()
    bid = seed_bank(cur, "B22")
    sid = seed_source(cur, bid)
    cid = seed_category(cur)
    rid = seed_run(cur, sid)
    oid = seed_obs(cur, sid, rid, cid)
    db.commit()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "UPDATE rate_observation SET reinterpretation_of_id = id WHERE id = %s", (oid,)
        )
