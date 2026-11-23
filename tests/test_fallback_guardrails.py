import uuid
import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

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

def test_native_newer_date_does_not_retire_different_category_active(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run1 = start_run(db, source_id)
    rec_txn = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("161.7825"),
        selling_rate=Decimal("165.0182"),
        category="transactional",
        effective_date=date(2026, 11, 5),
        effective_date_basis="source_published",
    )
    ingest(db, [rec_txn], source_id, run1, is_fallback=False)
    finish_run(db, run1, "success", records_found=1, records_accepted=1, is_fallback=False)

    run2 = start_run(db, source_id)
    rec_cash = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("161.7880"),
        selling_rate=Decimal("165.0238"),
        category="cash",
        effective_date=date(2026, 11, 6),
        effective_date_basis="source_published",
    )
    ingest(db, [rec_cash], source_id, run2, is_fallback=False)
    finish_run(db, run2, "success", records_found=1, records_accepted=1, is_fallback=False)

    with db.cursor() as cur:
        cur.execute("SELECT id, is_current, category_id FROM rate_observation WHERE collection_run_id = %s", (run1,))
        txn_row = cur.fetchone()
        assert txn_row[1] is True
        cur.execute("SELECT id, is_current, category_id FROM rate_observation WHERE collection_run_id = %s", (run2,))
        cash_row = cur.fetchone()
        assert cash_row[1] is True


def test_zero_records_triggers_fallback_without_unique_violation(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    mock_adapter = Mock()
    mock_adapter.parse.return_value = []

    fallback_records = [
        AdapterRecord(
            source_currency_code="USD",
            currency_name="US Dollar",
            buying_rate=Decimal("165.00"),
            selling_rate=Decimal("168.00"),
            category="cash",
            effective_date=date.today(),
            effective_date_basis="source_published",
        )
    ]
    mock_af = Mock()
    mock_af.fetch_raw.return_value = ("<html></html>", 200)
    mock_af.get_source_url.return_value = "https://addisfortune.news"
    mock_af.parse.return_value = (fallback_records, [])

    from scheduler.runner import Scheduler
    from infrastructure.adapter_registry import AdapterRegistry
    
    mock_registry = Mock(spec=AdapterRegistry)
    mock_registry.get.return_value = mock_adapter
    
    mock_response = Mock()
    mock_response.is_success.return_value = True
    mock_response.content = "<html></html>"
    mock_response.status_code = 200
    
    scheduler = Scheduler(adapter_registry=mock_registry)
    
    with patch("scheduler.runner._check_schema", return_value=False), \
         patch("adapters.addis_fortune.adapter.get_adapter_for_key", return_value=mock_af), \
         patch("scheduler.runner.RequestsHttpClient") as mock_http_class:
        mock_http_instance = Mock()
        mock_http_instance.fetch.return_value = mock_response
        mock_http_class.return_value = mock_http_instance
        
        res = scheduler.run_source(db, source_id)

    assert res["status"] in ("success", "partial_success")
    assert res["accepted"] == 1

    with db.cursor() as cur:
        cur.execute("SELECT status, error_code FROM collection_run WHERE source_id = %s ORDER BY id ASC", (source_id,))
        runs = cur.fetchall()
        assert len(runs) == 2
        assert runs[0][0] == "failed"
        assert runs[0][1] == "zero_records_extracted"
        assert runs[1][0] == "success"


def test_scoped_stale_orphan_observation_pruning(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    run_old = start_run(db, source_id)
    rec_old = AdapterRecord(
        source_currency_code="KES",
        currency_name="Kenyan Shilling",
        buying_rate=Decimal("1.20"),
        selling_rate=Decimal("1.25"),
        category="cash",
        effective_date=date.today() - timedelta(days=20),
        effective_date_basis="source_published",
    )
    ingest(db, [rec_old], source_id, run_old, is_fallback=False)
    finish_run(db, run_old, "success", records_found=1, records_accepted=1, is_fallback=False)

    from scheduler.runner import _expire_stale_fallback_current
    _expire_stale_fallback_current(db, source_id)

    with db.cursor() as cur:
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run_old,))
        assert cur.fetchone()[0] is True

    run_fresh = start_run(db, source_id)
    rec_fresh = AdapterRecord(
        source_currency_code="USD",
        currency_name="US Dollar",
        buying_rate=Decimal("165.00"),
        selling_rate=Decimal("168.00"),
        category="cash",
        effective_date=date.today(),
        effective_date_basis="source_published",
    )
    ingest(db, [rec_fresh], source_id, run_fresh, is_fallback=False)
    finish_run(db, run_fresh, "success", records_found=1, records_accepted=1, is_fallback=False)

    _expire_stale_fallback_current(db, source_id)

    with db.cursor() as cur:
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run_old,))
        assert cur.fetchone()[0] is False
        cur.execute("SELECT is_current FROM rate_observation WHERE collection_run_id = %s", (run_fresh,))
        assert cur.fetchone()[0] is True


def test_stale_feed_retained_when_no_fallback(db):
    bank_id, source_id, cat_id = _create_seed_data(db)
    stale_date = date.today() - timedelta(days=5)
    stale_records = [
        AdapterRecord(
            source_currency_code="USD",
            currency_name="US Dollar",
            buying_rate=Decimal("165.00"),
            selling_rate=Decimal("168.00"),
            category="cash",
            effective_date=stale_date,
            effective_date_basis="source_published",
        )
    ]
    mock_adapter = Mock()
    mock_adapter.parse.return_value = stale_records

    from scheduler.runner import Scheduler
    from infrastructure.adapter_registry import AdapterRegistry
    
    mock_registry = Mock(spec=AdapterRegistry)
    mock_registry.get.return_value = mock_adapter
    
    mock_response = Mock()
    mock_response.is_success.return_value = True
    mock_response.content = "<html></html>"
    mock_response.status_code = 200
    
    scheduler = Scheduler(adapter_registry=mock_registry)
    
    with patch("scheduler.runner._check_schema", return_value=False), \
         patch("adapters.addis_fortune.adapter.get_adapter_for_key", return_value=None), \
         patch("scheduler.runner.RequestsHttpClient") as mock_http_class:
        mock_http_instance = Mock()
        mock_http_instance.fetch.return_value = mock_response
        mock_http_class.return_value = mock_http_instance
        
        res = scheduler.run_source(db, source_id)

    assert res["status"] == "success"
    assert res["accepted"] == 1

    with db.cursor() as cur:
        cur.execute("SELECT status, error_code FROM collection_run WHERE source_id = %s ORDER BY id ASC", (source_id,))
        runs = cur.fetchall()
        assert len(runs) == 1
        assert runs[0][0] == "success"
        assert runs[0][1] == "stale_feed"



# ---------------------------------------------------------------------------
# P4 — Verification test: fallback caller must not retire non-fallback rows
# ---------------------------------------------------------------------------

def test_p4_fallback_caller_does_not_retire_non_fallback_row(db):
    """When _retire_prior_fallback_observations is called from the fallback path
    (is_fallback=True), it must retire only is_fallback=TRUE rows.
    A non-fallback row with an older effective_date must be left untouched.

    Setup: two current rows for the same source/currency, different categories
    so both can be is_current=TRUE simultaneously (the unique index is per
    source_id, source_currency_code, category_id):
      - fallback cash row    (is_fallback=TRUE,  effective_date=Oct 20)
      - non-fallback txn row (is_fallback=FALSE, effective_date=Oct 22)

    We call _retire_prior_fallback_observations with is_fallback=True and
    effective_date=Oct 27 (newer than both rows).

    Before P4 this test FAILS: the second OR arm
    (category_id IS NOT DISTINCT FROM %s AND effective_date < %s) has no
    is_fallback guard, so it also retires the non-fallback txn row when
    category_id matches (or when category_id IS NULL IS NOT DISTINCT FROM NULL).
    After P4 the fallback caller skips the second arm entirely.
    """
    from pipeline.ingest import _retire_prior_fallback_observations
    from pipeline.persist import insert_observation
    from pipeline.fingerprint import compute_fingerprint
    from pipeline.identity import build_identity
    from domain.enums import ValidationStatus, IdentityStatus
    from datetime import timezone

    bank_id, source_id, _ = _create_seed_data(db)
    run_id = start_run(db, source_id)

    # Resolve category ids.
    with db.cursor() as cur:
        cur.execute("SELECT id FROM rate_category WHERE code='cash'")
        cash_cat_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO rate_category (code, name, approved_at)
               VALUES ('transactional', 'Transactional', now())
               ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code RETURNING id"""
        )
        txn_cat_id = cur.fetchone()[0]

    fetched_at = datetime(2026, 10, 23, 8, 0, 0, tzinfo=timezone.utc)

    # Seed fallback cash row (is_current=TRUE, is_fallback=TRUE).
    fb_rec = AdapterRecord(
        source_currency_code="USD",
        buying_rate=Decimal("161.00"),
        selling_rate=Decimal("164.00"),
        category="cash",
        effective_date=date(2026, 10, 20),
        effective_date_basis="source_published",
    )
    fb_fp = compute_fingerprint(fb_rec, source_id, fetched_at.date())
    fb_lkey, fb_istatus = build_identity(fb_rec, source_id)
    fallback_id = insert_observation(
        conn=db, record=fb_rec, source_id=source_id, run_id=run_id,
        category_id=cash_cat_id, fingerprint=fb_fp, logical_key=fb_lkey,
        identity_status=fb_istatus, validation_status=ValidationStatus.VALIDATED,
        validation_messages=[], fetched_at=fetched_at,
        version_number=1, is_current=True, is_fallback=True,
    )

    # Seed non-fallback transactional row (is_current=TRUE, is_fallback=FALSE).
    # Different category_id so both rows can be current simultaneously.
    native_rec = AdapterRecord(
        source_currency_code="USD",
        buying_rate=Decimal("162.00"),
        selling_rate=Decimal("165.00"),
        category="transactional",
        effective_date=date(2026, 10, 22),
        effective_date_basis="source_published",
    )
    native_fp = compute_fingerprint(native_rec, source_id, fetched_at.date())
    native_lkey, native_istatus = build_identity(native_rec, source_id)
    native_id = insert_observation(
        conn=db, record=native_rec, source_id=source_id, run_id=run_id,
        category_id=txn_cat_id, fingerprint=native_fp, logical_key=native_lkey,
        identity_status=native_istatus, validation_status=ValidationStatus.VALIDATED,
        validation_messages=[], fetched_at=fetched_at,
        version_number=1, is_current=True, is_fallback=False,
    )
    finish_run(db, run_id, "success", records_found=2, records_accepted=2)

    # Call with is_fallback=True and a newer effective_date.
    # Before P4: the second OR arm retires the non-fallback txn row too
    #            (because txn_cat_id IS NOT DISTINCT FROM txn_cat_id AND Oct22 < Oct27).
    # After P4:  only the fallback cash row is retired (Oct20 < Oct27);
    #            the non-fallback txn row is untouched (Option B: date guard
    #            on fallback arm; non-fallback arm unchanged).
    _retire_prior_fallback_observations(
        db, source_id, "USD", txn_cat_id,
        effective_date=date(2026, 10, 27),
        is_fallback=True,
    )

    with db.cursor() as cur:
        cur.execute("SELECT is_current FROM rate_observation WHERE id=%s", (fallback_id,))
        assert cur.fetchone()[0] is False, "Fallback row should have been retired."

        cur.execute("SELECT is_current FROM rate_observation WHERE id=%s", (native_id,))
        assert cur.fetchone()[0] is True, (
            "Non-fallback row must NOT be retired when called from the fallback path."
        )
