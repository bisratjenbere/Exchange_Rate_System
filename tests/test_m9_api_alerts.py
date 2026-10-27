import json
import pytest
from decimal import Decimal
from datetime import datetime, date, timezone, timedelta
from unittest.mock import patch

SAMPLE_ROW = {
    "id": 1,
    "source_id": 1,
    "bank_name": "Test Bank",
    "bank_code": "TST",
    "source_currency_code": "USD",
    "currency_code": "USD",
    "category": "cash",
    "buying_rate": Decimal("165.0000000000"),
    "selling_rate": Decimal("167.0000000000"),
    "effective_date": date(2026, 10, 10),
    "fetched_at": datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc),
    "version_number": 1,
    "identity_status": "confirmed",
    "validation_status": "validated",
    "change_review_status": "not_required",
    "source_verification_status": "provisional",
    "has_pending_review": False,
    "staleness_warning": False,
    "is_provisional": True,
}

@pytest.fixture
def client():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from api.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def _mock_rates(rows):
    return patch("api.app.get_trusted_rates", return_value=rows)

def _mock_conn():
    return patch("api.app._conn")

from contextlib import contextmanager

@contextmanager
def _mock_ui_deps(rows=None, currencies=None, banks=None, matrix=None):
    from decimal import Decimal
    _rows = rows if rows is not None else [SAMPLE_ROW]
    _currencies = currencies or ["USD"]
    _banks = banks or [{"id": 1, "name": "Test Bank"}]
    _matrix = matrix if matrix is not None else {
        "currencies": ["USD"],
        "banks": ["Test Bank"],
        "matrix": {"USD": {"Test Bank": {"buying": Decimal("165"), "selling": Decimal("167"), "staleness_warning": False}}},
        "best_buying": {"USD": Decimal("165")},
    }
    _bank_data = {
        "bank_name": "Test Bank", "source_id": 1,
        "currencies": {"USD": {"cash": {"buying": Decimal("165"), "selling": Decimal("167"),
                                         "effective_date": date(2026,10,10),
                                         "fetched_at": datetime(2026,10,10,8,0,tzinfo=timezone.utc),
                                         "staleness_warning": False, "is_provisional": True,
                                         "has_pending_review": False}}},
        "latest_date": date(2026,10,10), "latest_fetch": datetime(2026,10,10,8,0,tzinfo=timezone.utc),
        "is_provisional": True, "staleness_warning": False, "categories": ["cash"],
    }
    with patch("api.app.get_trusted_rates", return_value=_rows), \
         patch("api.app.get_best_rates_by_currency", return_value=_rows), \
         patch("api.app.get_bank_rates_pivoted", return_value=_bank_data), \
         patch("api.app.get_currency_matrix", return_value=_matrix), \
         patch("api.app.get_available_currencies", return_value=_currencies), \
         patch("api.app.get_available_banks", return_value=_banks), \
         patch("api.app.get_search_suggestions", return_value={"currencies": _currencies, "banks": _banks}), \
         _mock_conn():
        yield

def test_health_ok(client):
    with _mock_conn():
        with patch("api.app.psycopg2.connect") as mock_connect:
            mock_connect.return_value.__enter__ = lambda s: s
            mock_connect.return_value.__exit__ = lambda *a: None
            mock_connect.return_value.cursor.return_value.__enter__ = lambda s: s
            mock_connect.return_value.cursor.return_value.__exit__ = lambda *a: None
            mock_connect.return_value.cursor.return_value.execute = lambda q: None
    resp = client.get("/health")
    assert resp.status_code in (200, 503)
    data = json.loads(resp.data)
    assert "status" in data

def test_rates_returns_json(client):
    with _mock_rates([SAMPLE_ROW]):
        with _mock_conn():
            resp = client.get("/rates")
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    assert isinstance(rows, list)
    assert rows[0]["currency_code"] == "USD"

def test_rates_source_id_filter(client):
    with _mock_rates([SAMPLE_ROW]):
        with _mock_conn():
            resp = client.get("/rates?source_id=1")
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    assert len(rows) == 1

def test_rates_path_form(client):
    with _mock_rates([SAMPLE_ROW]):
        with _mock_conn():
            resp = client.get("/rates/1")
    assert resp.status_code == 200

def test_rates_path_form_404(client):
    with _mock_rates([]):
        with _mock_conn():
            resp = client.get("/rates/999")
    assert resp.status_code == 404

def test_ui_renders(client):
    with _mock_ui_deps():
        resp = client.get("/?view=compare&currency=USD")
    assert resp.status_code == 200
    assert b"Test Bank" in resp.data
    assert b"PROVISIONAL" in resp.data

def test_ui_shows_bank_name(client):
    with _mock_ui_deps():
        resp = client.get("/?view=compare&currency=USD")
    assert b"Test Bank" in resp.data

def test_ui_compare_view(client):
    with _mock_ui_deps():
        resp = client.get("/?view=compare&currency=USD")
    assert resp.status_code == 200
    assert b"Test Bank" in resp.data
    assert b"USD" in resp.data

def test_ui_bank_view(client):
    with _mock_ui_deps():
        resp = client.get("/?view=bank&source_id=1")
    assert resp.status_code == 200
    assert b"Test Bank" in resp.data

def test_ui_all_view(client):
    with _mock_ui_deps():
        resp = client.get("/?view=all")
    assert resp.status_code == 200
    assert b"USD" in resp.data

def test_ui_shows_pending_review(client):
    row = {**SAMPLE_ROW, "has_pending_review": True, "is_provisional": False, "staleness_warning": False}
    with _mock_ui_deps(rows=[row]):
        resp = client.get("/?view=compare&currency=USD")
    assert resp.status_code == 200

def test_ui_shows_stale(client):
    row = {**SAMPLE_ROW, "staleness_warning": True, "is_provisional": False}
    with _mock_ui_deps(rows=[row]):
        resp = client.get("/?view=compare&currency=USD")
    assert b"STALE" in resp.data

def test_ui_no_rows(client):
    empty_matrix = {"currencies": [], "banks": [], "matrix": {}, "best_buying": {}}
    with _mock_ui_deps(rows=[], matrix=empty_matrix):
        resp = client.get("/?view=all&filter=all")
    assert b"No trusted rates" in resp.data

def test_banks_endpoint(client):
    with patch("api.app.get_available_banks", return_value=[{"id": 1, "name": "Test Bank"}]):
        with _mock_conn():
            resp = client.get("/banks")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data[0]["name"] == "Test Bank"

def test_rates_by_currency_endpoint(client):
    with patch("api.app.get_trusted_rates_by_currency", return_value=[SAMPLE_ROW]):
        with _mock_conn():
            resp = client.get("/rates/by-currency/USD")
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    assert rows[0]["source_currency_code"] == "USD"

def test_rates_by_currency_404(client):
    with patch("api.app.get_trusted_rates_by_currency", return_value=[]):
        with _mock_conn():
            resp = client.get("/rates/by-currency/XYZ")
    assert resp.status_code == 404

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.db_utils import get_conn, reset_schema, apply_migrations
from alerts.checker import (
    check_failed_runs,
    check_schema_changes,
    check_disappearing_data,
    check_stale_rates,
    run_all_checks,
)

@pytest.fixture(scope="module")
def db():
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()

def _insert_bank(conn, code="TST"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bank (code, name) VALUES (%s, %s) RETURNING id",
            (code, f"Test Bank {code}"),
        )
        return cur.fetchone()[0]

def _insert_source(conn, bank_id, adapter_key="tst", is_enabled=True,
                   last_success_at=None):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rate_source
                   (bank_id, source_url, collection_method, adapter_key,
                    is_enabled, last_success_at)
               VALUES (%s, 'http://example.com', 'html', %s, %s, %s)
               RETURNING id""",
            (bank_id, adapter_key, is_enabled, last_success_at),
        )
        return cur.fetchone()[0]

def _insert_run(conn, source_id, status, finished_at=None,
                records_found=1, error_code=None, error_summary=None):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO collection_run
                   (source_id, started_at, finished_at, status,
                    records_found, error_code, error_summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (source_id, now - timedelta(minutes=5),
             finished_at or now, status,
             records_found, error_code, error_summary),
        )
        return cur.fetchone()[0]

def _insert_raw_capture(conn, run_id, reason, captured_at=None):
    ts = captured_at or datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_capture
                   (collection_run_id, captured_at, capture_reason,
                    content_hash, retention_until)
               VALUES (%s, %s, %s, %s, now()::date + 90)""",
            (run_id, ts, reason, "a" * 64),
        )

def test_failed_run_detected(db):
    bank_id = _insert_bank(db, "FR1")
    src_id = _insert_source(db, bank_id, "fr1")
    _insert_run(db, src_id, "failed", error_code="parse_failure",
                error_summary="bad html")
    db.commit()
    alerts = check_failed_runs(db, since_hours=1)
    assert any(a["source_id"] == src_id for a in alerts)
    assert all(a["type"] == "failed_run" for a in alerts)

def test_failed_run_outside_window_ignored(db):
    bank_id = _insert_bank(db, "FR2")
    src_id = _insert_source(db, bank_id, "fr2")
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    _insert_run(db, src_id, "failed", finished_at=old)
    db.commit()
    alerts = check_failed_runs(db, since_hours=1)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_successful_run_not_alerted(db):
    bank_id = _insert_bank(db, "FR3")
    src_id = _insert_source(db, bank_id, "fr3")
    _insert_run(db, src_id, "success")
    db.commit()
    alerts = check_failed_runs(db, since_hours=1)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_schema_change_detected(db):
    bank_id = _insert_bank(db, "SC1")
    src_id = _insert_source(db, bank_id, "sc1")
    run_id = _insert_run(db, src_id, "failed")
    _insert_raw_capture(db, run_id, "schema_change")
    db.commit()
    alerts = check_schema_changes(db, since_hours=1)
    assert any(a["source_id"] == src_id for a in alerts)
    assert all(a["type"] == "schema_change" for a in alerts)

def test_schema_change_outside_window_ignored(db):
    bank_id = _insert_bank(db, "SC2")
    src_id = _insert_source(db, bank_id, "sc2")
    run_id = _insert_run(db, src_id, "failed")
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    _insert_raw_capture(db, run_id, "schema_change", captured_at=old)
    db.commit()
    alerts = check_schema_changes(db, since_hours=1)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_other_capture_reason_not_schema_alert(db):
    bank_id = _insert_bank(db, "SC3")
    src_id = _insert_source(db, bank_id, "sc3")
    run_id = _insert_run(db, src_id, "failed")
    _insert_raw_capture(db, run_id, "parse_failure")
    db.commit()
    alerts = check_schema_changes(db, since_hours=1)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_disappearing_data_detected(db):
    bank_id = _insert_bank(db, "DD1")
    src_id = _insert_source(db, bank_id, "dd1", is_enabled=True)
    _insert_run(db, src_id, "success", records_found=0)
    db.commit()
    alerts = check_disappearing_data(db)
    assert any(a["source_id"] == src_id for a in alerts)
    assert all(a["type"] == "disappearing_data" for a in alerts)

def test_disappearing_data_not_triggered_with_records(db):
    bank_id = _insert_bank(db, "DD2")
    src_id = _insert_source(db, bank_id, "dd2", is_enabled=True)
    _insert_run(db, src_id, "success", records_found=5)
    db.commit()
    alerts = check_disappearing_data(db)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_disappearing_data_disabled_source_ignored(db):
    bank_id = _insert_bank(db, "DD3")
    src_id = _insert_source(db, bank_id, "dd3", is_enabled=False)
    _insert_run(db, src_id, "success", records_found=0)
    db.commit()
    alerts = check_disappearing_data(db)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_stale_never_succeeded(db):
    bank_id = _insert_bank(db, "SR1")
    src_id = _insert_source(db, bank_id, "sr1", is_enabled=True,
                             last_success_at=None)
    db.commit()
    alerts = check_stale_rates(db, stale_hours=1)
    assert any(a["source_id"] == src_id for a in alerts)
    assert all(a["type"] == "stale_rates" for a in alerts)

def test_stale_old_success(db):
    bank_id = _insert_bank(db, "SR2")
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    src_id = _insert_source(db, bank_id, "sr2", is_enabled=True,
                             last_success_at=old)
    db.commit()
    alerts = check_stale_rates(db, stale_hours=1)
    assert any(a["source_id"] == src_id for a in alerts)

def test_stale_recent_success_not_alerted(db):
    bank_id = _insert_bank(db, "SR3")
    recent = datetime.now(timezone.utc) - timedelta(minutes=30)
    src_id = _insert_source(db, bank_id, "sr3", is_enabled=True,
                             last_success_at=recent)
    db.commit()
    alerts = check_stale_rates(db, stale_hours=1)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_stale_disabled_source_ignored(db):
    bank_id = _insert_bank(db, "SR4")
    src_id = _insert_source(db, bank_id, "sr4", is_enabled=False,
                             last_success_at=None)
    db.commit()
    alerts = check_stale_rates(db, stale_hours=1)
    assert not any(a["source_id"] == src_id for a in alerts)

def test_run_all_checks_returns_list(db):
    alerts = run_all_checks(db, since_hours=1, stale_hours=1)
    assert isinstance(alerts, list)
    for a in alerts:
        assert "type" in a
        assert "source_id" in a
        assert "detail" in a
