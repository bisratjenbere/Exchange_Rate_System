import uuid
import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock

from tests.db_utils import get_conn, apply_migrations, reset_schema
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from pipeline.ingest import ingest
from pipeline.runs import start_run, finish_run, reap_stuck_runs
from scheduler.runner import _fetch_with_retry

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

def _create_seed_data(conn):
    code = f"TB_{uuid.uuid4().hex[:8].upper()}"
    with conn.cursor() as cur:
        cur.execute("INSERT INTO bank (code, name) VALUES (%s, %s) RETURNING id", (code, f"Bank {code}"))
        bank_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO rate_source (bank_id, source_url, collection_method, adapter_key, verification_status)
               VALUES (%s, 'https://testbank.com', 'api', 'test_adapter', 'provisional') RETURNING id""",
            (bank_id,)
        )
        source_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM rate_category WHERE code = 'cash'")
        row = cur.fetchone()
        cash_cat_id = row[0] if row else 1
    return bank_id, source_id, cash_cat_id

def test_anti_poisoning_older_fallback_does_not_overwrite_primary(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run_primary = start_run(db, source_id)
    
    primary_record = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("120.50"),
        selling_rate=Decimal("122.50"),
        category="cash",
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
    )
    res_primary = ingest(db, [primary_record], source_id, run_primary, is_fallback=False)
    assert res_primary.accepted == 1
    finish_run(db, run_primary, "success", records_found=1, records_accepted=1, is_fallback=False)
    
    with db.cursor() as cur:
        cur.execute("SELECT id, is_current, is_fallback, effective_date FROM rate_observation WHERE collection_run_id = %s", (run_primary,))
        prim_obs = cur.fetchone()
        assert prim_obs[1] is True
        assert prim_obs[2] is False
        assert prim_obs[3] == date(2026, 10, 26)

    run_fallback = start_run(db, source_id)
    fallback_record = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("119.00"),
        selling_rate=Decimal("121.00"),
        category="cash",
        effective_date=date(2026, 10, 24),
        effective_date_basis="source_published",
    )
    res_fallback = ingest(db, [fallback_record], source_id, run_fallback, is_fallback=True)
    assert res_fallback.accepted == 1
    finish_run(db, run_fallback, "success", records_found=1, records_accepted=1, is_fallback=True, fallback_adapter="addis_fortune")
    
    with db.cursor() as cur:
        cur.execute("SELECT id, is_current, is_fallback, effective_date FROM rate_observation WHERE collection_run_id = %s", (run_fallback,))
        fb_obs = cur.fetchone()
        assert fb_obs[1] is False
        assert fb_obs[2] is True
        assert fb_obs[3] == date(2026, 10, 24)

        cur.execute("SELECT is_current FROM rate_observation WHERE id = %s", (prim_obs[0],))
        assert cur.fetchone()[0] is True

def test_anti_poisoning_same_date_primary_wins(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run_primary = start_run(db, source_id)
    
    primary_record = AdapterRecord(
        source_currency_code="EUR",
        currency_name="Euro",
        buying_rate=Decimal("130.00"),
        selling_rate=Decimal("132.00"),
        category="cash",
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
    )
    ingest(db, [primary_record], source_id, run_primary, is_fallback=False)
    finish_run(db, run_primary, "success", records_found=1, records_accepted=1, is_fallback=False)
    
    run_fallback = start_run(db, source_id)
    fallback_record = AdapterRecord(
        source_currency_code="EUR",
        currency_name="Euro",
        buying_rate=Decimal("129.50"),
        selling_rate=Decimal("131.50"),
        category="cash",
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
    )
    ingest(db, [fallback_record], source_id, run_fallback, is_fallback=True)
    finish_run(db, run_fallback, "success", records_found=1, records_accepted=1, is_fallback=True, fallback_adapter="addis_fortune")
    
    with db.cursor() as cur:
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run_primary,))
        assert cur.fetchone()[0] is True
        cur.execute("SELECT is_current, is_fallback FROM rate_observation WHERE collection_run_id = %s", (run_fallback,))
        row = cur.fetchone()
        assert row[0] is False
        assert row[1] is True

def test_fallback_promotes_when_newer(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run_primary = start_run(db, source_id)
    
    primary_record = AdapterRecord(
        source_currency_code="GBP",
        currency_name="Pound Sterling",
        buying_rate=Decimal("150.00"),
        selling_rate=Decimal("153.00"),
        category="cash",
        effective_date=date(2026, 10, 20),
        effective_date_basis="source_published",
    )
    ingest(db, [primary_record], source_id, run_primary, is_fallback=False)
    finish_run(db, run_primary, "success", records_found=1, records_accepted=1, is_fallback=False)
    
    run_fallback = start_run(db, source_id)
    fallback_record = AdapterRecord(
        source_currency_code="GBP",
        currency_name="Pound Sterling",
        buying_rate=Decimal("155.00"),
        selling_rate=Decimal("158.00"),
        category="cash",
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
    )
    ingest(db, [fallback_record], source_id, run_fallback, is_fallback=True)
    finish_run(db, run_fallback, "success", records_found=1, records_accepted=1, is_fallback=True, fallback_adapter="addis_fortune")
    
    with db.cursor() as cur:
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run_primary,))
        assert cur.fetchone()[0] is False
        cur.execute("SELECT is_current, is_fallback FROM rate_observation WHERE collection_run_id = %s", (run_fallback,))
        row = cur.fetchone()
        assert row[0] is True
        assert row[1] is True

def test_metric_separation_duplicates_and_flagged(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run1 = start_run(db, source_id)
    
    record = AdapterRecord(
        source_currency_code="SAR",
        currency_name="Saudi Riyal",
        buying_rate=Decimal("32.00"),
        selling_rate=Decimal("33.00"),
        category="cash",
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
    )
    res1 = ingest(db, [record], source_id, run1, is_fallback=False)
    assert res1.accepted == 1
    assert res1.duplicates == 0
    finish_run(db, run1, "success", records_found=1, records_accepted=res1.accepted,
               records_flagged=res1.flagged, records_duplicated=res1.duplicates, is_fallback=False)
    
    run2 = start_run(db, source_id)
    res2 = ingest(db, [record], source_id, run2, is_fallback=False)
    assert res2.accepted == 0
    assert res2.duplicates == 1
    finish_run(db, run2, "success", records_found=1, records_accepted=res2.accepted,
               records_flagged=res2.flagged, records_duplicated=res2.duplicates, is_fallback=False)
    
    with db.cursor() as cur:
        cur.execute("SELECT records_accepted, records_flagged, records_duplicated, is_fallback FROM collection_run WHERE id = %s", (run2,))
        row = cur.fetchone()
        assert row[0] == 0
        assert row[1] == 0
        assert row[2] == 1
        assert row[3] is False

def test_reap_stuck_runs(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO collection_run (source_id, started_at, status)
               VALUES (%s, now() - INTERVAL '15 minutes', 'running') RETURNING id""",
            (source_id,)
        )
        stuck_id = cur.fetchone()[0]
    
    reaped_count = reap_stuck_runs(db, threshold_minutes=5)
    assert reaped_count >= 1
    
    with db.cursor() as cur:
        cur.execute("SELECT status, error_code, error_summary, finished_at FROM collection_run WHERE id = %s", (stuck_id,))
        row = cur.fetchone()
        assert row[0] == "failed"
        assert row[1] == "timeout_reaped"
        assert row[3] is not None

def test_fetch_with_retry_succeeds_on_transient_error():
    mock_fn = Mock()
    mock_fn.side_effect = [RuntimeError("HTTPSConnectionPool: Read timed out"), "<html>Rates</html>"]
    
    result = _fetch_with_retry(mock_fn, retries=1, backoff=0.01)
    assert result == "<html>Rates</html>"
    assert mock_fn.call_count == 2

def test_fetch_with_retry_raises_on_persistent_error():
    mock_fn = Mock()
    mock_fn.side_effect = [RuntimeError("Read timed out"), RuntimeError("Read timed out")]
    
    with pytest.raises(RuntimeError):
        _fetch_with_retry(mock_fn, retries=1, backoff=0.01)
    assert mock_fn.call_count == 2

def test_native_success_retires_prior_fallback_across_all_categories(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run_fb = start_run(db, source_id)
    fb_cash = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("161.00"),
        selling_rate=Decimal("164.00"),
        category="cash",
        effective_date=date(2026, 10, 24),
        effective_date_basis="source_published",
    )
    fb_txn = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("161.00"),
        selling_rate=Decimal("164.00"),
        category="transactional",
        effective_date=date(2026, 10, 24),
        effective_date_basis="source_published",
    )
    ingest(db, [fb_cash, fb_txn], source_id, run_fb, is_fallback=True)
    finish_run(db, run_fb, "success", records_found=2, records_accepted=2, is_fallback=True, fallback_adapter="addis_fortune")

    with db.cursor() as cur:
        cur.execute("SELECT category_id, is_current FROM rate_observation WHERE collection_run_id = %s", (run_fb,))
        rows = cur.fetchall()
        assert len(rows) == 2
        assert all(r[1] is True for r in rows)

    run_native = start_run(db, source_id)
    native_txn = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("162.00"),
        selling_rate=Decimal("165.00"),
        category="transactional",
        effective_date=date(2026, 10, 27),
        effective_date_basis="source_published",
    )
    ingest(db, [native_txn], source_id, run_native, is_fallback=False)
    finish_run(db, run_native, "success", records_found=1, records_accepted=1, is_fallback=False)

    with db.cursor() as cur:
        cur.execute("SELECT id, is_current FROM rate_observation WHERE collection_run_id = %s", (run_native,))
        assert cur.fetchone()[1] is True
        cur.execute("SELECT id, is_current FROM rate_observation WHERE collection_run_id = %s", (run_fb,))
        fb_rows = cur.fetchall()
        assert len(fb_rows) == 2
        assert all(r[1] is False for r in fb_rows)

def test_older_native_does_not_overwrite_newer_active(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run1 = start_run(db, source_id)
    rec_oct26 = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("162.00"),
        selling_rate=Decimal("165.00"),
        category="transactional",
        effective_date=date(2026, 10, 26),
        effective_date_basis="source_published",
    )
    ingest(db, [rec_oct26], source_id, run1, is_fallback=False)
    finish_run(db, run1, "success", records_found=1, records_accepted=1, is_fallback=False)

    run2 = start_run(db, source_id)
    rec_sep30 = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("160.00"),
        selling_rate=Decimal("163.00"),
        category="transactional",
        effective_date=date(2026, 9, 30),
        effective_date_basis="source_published",
    )
    ingest(db, [rec_sep30], source_id, run2, is_fallback=False)
    finish_run(db, run2, "success", records_found=1, records_accepted=1, is_fallback=False)

    with db.cursor() as cur:
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run1,))
        assert cur.fetchone()[0] is True
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run2,))
        assert cur.fetchone()[0] is False
