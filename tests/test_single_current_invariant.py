import pytest
import psycopg2
from decimal import Decimal
from datetime import date, datetime, timezone, timedelta
from tests.db_utils import get_conn, reset_schema, apply_migrations
from pipeline.ingest import ingest
from domain.records import AdapterRecord
from trusted_view.query import get_bank_rates_pivoted

@pytest.fixture(scope="module")
def db():
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()

def _seed_bank(conn, code="TST"):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO bank (code, name) VALUES (%s, %s) RETURNING id",
                    (code, f"Test Bank {code}"))
        return cur.fetchone()[0]

def _seed_source(conn, bank_id, adapter_key="tst"):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO rate_source
                           (bank_id, source_url, collection_method, adapter_key, is_enabled)
                       VALUES (%s, 'http://test.com', 'html', %s, TRUE) RETURNING id""",
                    (bank_id, adapter_key))
        return cur.fetchone()[0]

def _seed_run(conn, source_id):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO collection_run
                           (source_id, started_at, finished_at, status, records_found)
                       VALUES (%s, %s, %s, 'running', 1) RETURNING id""",
                    (source_id, now, now))
        return cur.fetchone()[0]

def test_unique_constraint_rejects_second_active_rate(db):
    cur = db.cursor()
    bid = _seed_bank(db, "U1")
    sid = _seed_source(db, bid, "u1")
    rid = _seed_run(db, sid)
    
    cur.execute("""
        INSERT INTO rate_observation (
            source_id, collection_run_id, category_id, currency_code, source_currency_code,
            buying_rate, selling_rate, effective_date, effective_date_basis, fetched_at,
            snapshot_fingerprint, fingerprint_version, is_current, logical_observation_key, identity_status, validation_status
        ) VALUES (
            %s, %s, 1, 'USD', 'USD',
            160.0, 162.0, '2026-10-24', 'source_published', NOW(),
            'fp1', 2, TRUE, 'u1:USD:cash:2026-10-24', 'confirmed', 'validated'
        )
    """, (sid, rid))
    db.commit()

    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("""
            INSERT INTO rate_observation (
                source_id, collection_run_id, category_id, currency_code, source_currency_code,
                buying_rate, selling_rate, effective_date, effective_date_basis, fetched_at,
                snapshot_fingerprint, fingerprint_version, is_current, logical_observation_key, identity_status, validation_status
            ) VALUES (
                %s, %s, 1, 'USD', 'USD',
                161.0, 163.0, '2026-10-26', 'source_published', NOW(),
                'fp2', 2, TRUE, 'u1:USD:cash:2026-10-26', 'confirmed', 'validated'
            )
        """, (sid, rid))
    db.rollback()

def test_ingest_newer_rate_retires_older_active_rate(db):
    bid = _seed_bank(db, "U2")
    sid = _seed_source(db, bid, "u2")
    rid1 = _seed_run(db, sid)

    rec1 = AdapterRecord(
        source_currency_code="USD",
        currency_name=None,
        category="cash",
        buying_rate=Decimal("160.00"),
        selling_rate=Decimal("162.00"),
        source_rate_text="160/162",
        raw_excerpt={},
        effective_date=date(2026, 10, 24),
        effective_date_basis="source_published",
        quote_currency_code="ETB",
        unit_multiplier=Decimal("1"),
    )
    res1 = ingest(db, [rec1], sid, rid1, fetched_at=datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc))
    assert res1.accepted == 1
    db.commit()

    with db.cursor() as cur:
        cur.execute("SELECT id, is_current, effective_date FROM rate_observation WHERE source_id=%s AND is_current=TRUE", (sid,))
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][2] == date(2026, 10, 24)
        obs1_id = rows[0][0]

    with db.cursor() as cur:
        cur.execute("UPDATE collection_run SET status='success' WHERE id=%s", (rid1,))
    db.commit()

    rid2 = _seed_run(db, sid)
    rec2 = AdapterRecord(
        source_currency_code="USD",
        currency_name=None,
        category="cash",
        buying_rate=Decimal("161.50"),
        selling_rate=Decimal("163.50"),
        source_rate_text="161.5/163.5",
        raw_excerpt={},
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
        quote_currency_code="ETB",
        unit_multiplier=Decimal("1"),
    )
    res2 = ingest(db, [rec2], sid, rid2, fetched_at=datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc))
    assert res2.accepted == 1
    db.commit()

    with db.cursor() as cur:
        cur.execute("SELECT id, is_current, effective_date FROM rate_observation WHERE source_id=%s AND is_current=TRUE", (sid,))
        active_rows = cur.fetchall()
        assert len(active_rows) == 1
        assert active_rows[0][2] == date(2026, 10, 26)

        cur.execute("SELECT is_current FROM rate_observation WHERE id=%s", (obs1_id,))
        assert cur.fetchone()[0] is False

def test_pivoted_view_returns_latest_date_when_both_present(db):
    bid = _seed_bank(db, "U3")
    sid = _seed_source(db, bid, "u3")
    rid = _seed_run(db, sid)

    rec1 = AdapterRecord(
        source_currency_code="USD",
        currency_name=None,
        category="cash",
        buying_rate=Decimal("161.3978"),
        selling_rate=Decimal("164.6258"),
        source_rate_text="161.3978/164.6258",
        raw_excerpt={},
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
        quote_currency_code="ETB",
        unit_multiplier=Decimal("1"),
    )
    ingest(db, [rec1], sid, rid, fetched_at=datetime(2026, 10, 26, 11, 0, tzinfo=timezone.utc))
    db.commit()

    pivoted = get_bank_rates_pivoted(db, sid)
    assert pivoted["currencies"]["USD"]["cash"]["buying"] == Decimal("161.3978")
    assert pivoted["currencies"]["USD"]["cash"]["selling"] == Decimal("164.6258")
    assert pivoted["currencies"]["USD"]["cash"]["effective_date"] == date(2026, 10, 26)

def test_review_approval_does_not_overwrite_newer_active_rate(db):
    bid = _seed_bank(db, "U4")
    sid = _seed_source(db, bid, "u4")
    rid = _seed_run(db, sid)

    with db.cursor() as cur:
        # 1. Existing active rate for Monday Oct 26
        cur.execute("""
            INSERT INTO rate_observation (
                source_id, collection_run_id, category_id, currency_code, source_currency_code,
                buying_rate, selling_rate, effective_date, effective_date_basis, fetched_at,
                snapshot_fingerprint, fingerprint_version, is_current, logical_observation_key, identity_status, validation_status
            ) VALUES (
                %s, %s, 1, 'USD', 'USD',
                161.3978, 164.6258, '2026-10-26', 'source_published', NOW(),
                'fp_mon', 2, TRUE, 'u4:USD:cash:2026-10-26', 'confirmed', 'validated'
            ) RETURNING id
        """, (sid, rid))
        mon_id = cur.fetchone()[0]

        # 2. Older candidate for Saturday Oct 24 in pending review
        cur.execute("""
            INSERT INTO rate_observation (
                source_id, collection_run_id, category_id, currency_code, source_currency_code,
                buying_rate, selling_rate, effective_date, effective_date_basis, fetched_at,
                snapshot_fingerprint, fingerprint_version, is_current, logical_observation_key, identity_status, validation_status, change_review_status
            ) VALUES (
                %s, %s, 1, 'USD', 'USD',
                161.3928, 164.6207, '2026-10-24', 'source_published', NOW(),
                'fp_sat', 2, FALSE, 'u4:USD:cash:2026-10-24', 'confirmed', 'validated', 'pending_review'
            ) RETURNING id
        """, (sid, rid))
        sat_id = cur.fetchone()[0]
    db.commit()

    from unittest.mock import patch
    from api.app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        with patch("api.app._conn", return_value=db):
            resp = client.post("/review/decide", data={"obs_id": [sat_id], "decision": "approve"})
            assert resp.status_code == 302

    with db.cursor() as cur:
        # Monday record must STILL be current!
        cur.execute("SELECT is_current FROM rate_observation WHERE id=%s", (mon_id,))
        assert cur.fetchone()[0] is True

        # Saturday record must NOT be current!
        cur.execute("SELECT is_current, change_review_status FROM rate_observation WHERE id=%s", (sat_id,))
        sat_status = cur.fetchone()
        assert sat_status[0] is False
        assert sat_status[1] == "new_publication"
