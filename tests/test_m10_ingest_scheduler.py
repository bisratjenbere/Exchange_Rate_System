import hashlib
import json
import pytest
from datetime import datetime, timezone, date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tests.db_utils import get_conn, reset_schema, apply_migrations
from domain.records import AdapterRecord
from pipeline.ingest import ingest, IngestResult

@pytest.fixture(scope="module")
def db():
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()

def _make_bank(conn, code):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bank (code, name) VALUES (%s, %s) RETURNING id",
            (code, f"Bank {code}"),
        )
        return cur.fetchone()[0]

def _make_source(conn, bank_id, adapter_key="tst"):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rate_source
                   (bank_id, source_url, collection_method, adapter_key, is_enabled)
               VALUES (%s, 'http://example.com', 'html', %s, TRUE)
               RETURNING id""",
            (bank_id, adapter_key),
        )
        return cur.fetchone()[0]

def _make_run(conn, source_id):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO collection_run (source_id, started_at, status)
               VALUES (%s, now(), 'running') RETURNING id""",
            (source_id,),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id

def _finish_run(conn, run_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE collection_run SET status='success', finished_at=now() WHERE id=%s",
            (run_id,),
        )
    conn.commit()

def _record(currency="USD", buying="165.00", selling="167.00",
            category="cash", date_basis="source_published",
            effective_date=None):
    return AdapterRecord(
        source_currency_code=currency,
        category=category,
        buying_rate=Decimal(buying) if buying else None,
        selling_rate=Decimal(selling) if selling else None,
        effective_date=effective_date or date(2026, 10, 10),
        effective_date_basis=date_basis,
        source_record_key=f"key-{currency}",
        source_rate_text=f"{buying}/{selling}",
    )

def test_ingest_new_record_accepted(db):
    bank_id = _make_bank(db, "IG1")
    src_id = _make_source(db, bank_id, "ig1")
    run_id = _make_run(db, src_id)

    result = ingest(db, [_record()], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.accepted == 1
    assert result.rejected == 0
    assert result.duplicates == 0

def test_ingest_duplicate_skipped(db):
    bank_id = _make_bank(db, "IG2")
    src_id = _make_source(db, bank_id, "ig2")
    run_id = _make_run(db, src_id)

    rec = _record(currency="EUR")
    ingest(db, [rec], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    run_id2 = _make_run(db, src_id)
    result = ingest(db, [rec], src_id, run_id2)
    db.commit()
    _finish_run(db, run_id2)

    assert result.duplicates == 1
    assert result.accepted == 0

def test_ingest_duplicate_promotes_fallback(db):
    bank_id = _make_bank(db, "IGFB")
    src_id = _make_source(db, bank_id, "igfb")
    run_id1 = _make_run(db, src_id)

    rec = _record(currency="USD")
    res1 = ingest(db, [rec], src_id, run_id1, is_fallback=True)
    db.commit()
    _finish_run(db, run_id1)
    assert res1.accepted == 1

    with db.cursor() as cur:
        cur.execute("SELECT is_fallback, is_current FROM rate_observation WHERE source_id = %s", (src_id,))
        row = cur.fetchone()
        assert row[0] is True
        assert row[1] is True

    run_id2 = _make_run(db, src_id)
    res2 = ingest(db, [rec], src_id, run_id2, is_fallback=False)
    db.commit()
    _finish_run(db, run_id2)

    assert res2.duplicates == 1
    with db.cursor() as cur:
        cur.execute("SELECT is_fallback, is_current FROM rate_observation WHERE source_id = %s", (src_id,))
        row = cur.fetchone()
        assert row[0] is False
        assert row[1] is True

def test_ingest_intraday_update_auto_promoted(db):
    bank_id = _make_bank(db, "IG3A")
    src_id = _make_source(db, bank_id, "ig3a")
    run_id = _make_run(db, src_id)

    rec1 = _record(currency="GBP", buying="165.00", selling="167.00")
    res1 = ingest(db, [rec1], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)
    assert res1.accepted == 1

    run_id2 = _make_run(db, src_id)
    rec2 = _record(currency="GBP", buying="166.00", selling="168.00")
    result = ingest(db, [rec2], src_id, run_id2)
    db.commit()
    _finish_run(db, run_id2)

    assert result.candidates == 0
    assert result.accepted == 1

    cur = db.cursor()
    cur.execute("SELECT id, is_current, version_number, supersedes_id FROM rate_observation WHERE source_id=%s ORDER BY id", (src_id,))
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0][1] is False
    assert rows[0][2] == 1
    assert rows[1][1] is True
    assert rows[1][2] == 2
    assert rows[1][3] == rows[0][0]

def test_ingest_intraday_anomaly_quarantined(db):
    bank_id = _make_bank(db, "IG3B")
    src_id = _make_source(db, bank_id, "ig3b")
    run_id = _make_run(db, src_id)

    rec1 = _record(currency="GBP", buying="165.00", selling="167.00")
    ingest(db, [rec1], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    run_id2 = _make_run(db, src_id)
    rec2_anomaly = _record(currency="GBP", buying="168.00", selling="165.00")
    result = ingest(db, [rec2_anomaly], src_id, run_id2)
    db.commit()
    _finish_run(db, run_id2)

    assert result.candidates == 1
    assert result.accepted == 0

    cur = db.cursor()
    cur.execute("SELECT id, is_current FROM rate_observation WHERE source_id=%s ORDER BY id", (src_id,))
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0][1] is True
    assert rows[1][1] is False

def test_ingest_rejected_record_counted(db):
    bank_id = _make_bank(db, "IG4")
    src_id = _make_source(db, bank_id, "ig4")
    run_id = _make_run(db, src_id)

    bad = AdapterRecord(
        source_currency_code="JPY",
        category="cash",
        buying_rate=None,
        selling_rate=None,
        effective_date=date(2026, 10, 10),
        effective_date_basis="source_published",
    )
    result = ingest(db, [bad], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.rejected == 1
    assert result.accepted == 0

def test_ingest_unknown_category_flagged(db):
    bank_id = _make_bank(db, "IG5")
    src_id = _make_source(db, bank_id, "ig5")
    run_id = _make_run(db, src_id)

    rec = _record(currency="CHF", category="UNKNOWN")
    result = ingest(db, [rec], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.flagged == 1
    assert result.accepted == 0

def test_ingest_ambiguous_identity_flagged(db):
    bank_id = _make_bank(db, "IG6")
    src_id = _make_source(db, bank_id, "ig6")
    run_id = _make_run(db, src_id)

    rec = _record(currency="SAR", date_basis="unknown", effective_date=None)
    rec.effective_date = None
    result = ingest(db, [rec], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.flagged == 1

def test_ingest_suspicious_data_flagged(db):
    bank_id = _make_bank(db, "IG7")
    src_id = _make_source(db, bank_id, "ig7")
    run_id = _make_run(db, src_id)

    rec = _record(currency="AED", buying="168.00", selling="165.00")
    result = ingest(db, [rec], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.suspicious is True

def test_ingest_multiple_records_mixed(db):
    bank_id = _make_bank(db, "IG8")
    src_id = _make_source(db, bank_id, "ig8")
    run_id = _make_run(db, src_id)

    records = [
        _record(currency="USD"),
        _record(currency="EUR"),
        AdapterRecord(
            source_currency_code="BAD",
            category="cash",
            buying_rate=None,
            selling_rate=None,
            effective_date=date(2026, 10, 10),
            effective_date_basis="source_published",
        ),
    ]
    result = ingest(db, records, src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.accepted == 2
    assert result.rejected == 1

def test_ingest_empty_list(db):
    bank_id = _make_bank(db, "IG9")
    src_id = _make_source(db, bank_id, "ig9")
    run_id = _make_run(db, src_id)

    result = ingest(db, [], src_id, run_id)
    db.commit()
    _finish_run(db, run_id)

    assert result.accepted == 0
    assert result.rejected == 0
    assert result.duplicates == 0

from scheduler.runner import (
    run_source, run_all, _load_adapter, _parse, _run_status, _classify_error,
)

def test_load_adapter_cbe():
    adapter = _load_adapter("cbe_api")
    assert hasattr(adapter, "parse")

def test_load_adapter_adib():
    adapter = _load_adapter("adib_api")
    assert hasattr(adapter, "parse")

def test_load_adapter_unknown_raises():
    with pytest.raises(ImportError):
        _load_adapter("nonexistent_bank_xyz")

def test_parse_plain_list():
    mock_adapter = MagicMock()
    mock_adapter.parse.return_value = [_record()]
    result = _parse(mock_adapter, "raw")
    assert len(result) == 1

def test_parse_tuple_return():
    mock_adapter = MagicMock()
    mock_adapter.parse.return_value = ([_record()], ["err1"])
    result = _parse(mock_adapter, "raw")
    assert len(result) == 1

def test_run_status_all_accepted():
    r = IngestResult(accepted=5)
    assert _run_status(r) == "success"

def test_run_status_some_rejected():
    r = IngestResult(accepted=3, rejected=1)
    assert _run_status(r) == "partial_success"

def test_run_status_all_rejected():
    r = IngestResult(accepted=0, rejected=3)
    assert _run_status(r) == "failed"

def test_classify_error_http():
    import requests
    exc = requests.exceptions.ConnectionError("refused")
    code, _ = _classify_error(exc)
    assert code == "http_failure"

def test_classify_error_parse():
    exc = ValueError("bad html")
    code, _ = _classify_error(exc)
    assert code == "parse_failure"

def test_classify_error_schema():
    exc = ValueError("Schema fingerprint changed")
    code, _ = _classify_error(exc)
    assert code == "schema_change"

def test_run_source_success(db):
    bank_id = _make_bank(db, "RS1")
    src_id = _make_source(db, bank_id, "rs1")
    db.commit()

    fixture_records = [_record(currency="USD", effective_date=date.today())]

    mock_adapter = MagicMock()
    mock_adapter.parse.return_value = fixture_records

    with patch("scheduler.runner._fetch", return_value=('{"ok":true}', 200)), \
         patch("scheduler.runner._load_adapter", return_value=mock_adapter), \
         patch("scheduler.runner._check_schema"):
        result = run_source(db, src_id)

    assert result["status"] in ("success", "partial_success")
    assert result["accepted"] >= 0

def test_run_source_http_failure(db):
    bank_id = _make_bank(db, "RS2")
    src_id = _make_source(db, bank_id, "rs2")
    db.commit()

    import requests
    with patch("scheduler.runner._fetch",
               side_effect=requests.exceptions.ConnectionError("refused")):
        result = run_source(db, src_id)

    assert result["status"] == "failed"
    assert result["error_code"] == "http_failure"

def test_run_source_parse_failure(db):
    bank_id = _make_bank(db, "RS3")
    src_id = _make_source(db, bank_id, "rs3")
    db.commit()

    mock_adapter = MagicMock()
    mock_adapter.parse.side_effect = ValueError("bad html")

    with patch("scheduler.runner._fetch", return_value=("<html>", 200)), \
         patch("scheduler.runner._load_adapter", return_value=mock_adapter), \
         patch("scheduler.runner._check_schema"):
        result = run_source(db, src_id)

    assert result["status"] == "failed"
    assert result["error_code"] == "parse_failure"

def test_run_source_not_found(db):
    result = run_source(db, 999999)
    assert result["status"] == "error"

def test_run_all_iterates_enabled(db):
    bank_id = _make_bank(db, "RA1")
    src_id = _make_source(db, bank_id, "ra1")
    db.commit()

    mock_adapter = MagicMock()
    mock_adapter.parse.return_value = []

    with patch("scheduler.runner._fetch", return_value=("{}", 200)), \
         patch("scheduler.runner._load_adapter", return_value=mock_adapter), \
         patch("scheduler.runner._check_schema"), \
         patch("scheduler.runner.time.sleep"):
        results = run_all(db)

    assert isinstance(results, list)
    assert any(r["source_id"] == src_id for r in results)


def test_zero_records_without_fallback_marks_run_failed(db):
    bank_id = _make_bank(db, "ZR1")
    src_id = _make_source(db, bank_id, "zr1")
    db.commit()

    mock_adapter = MagicMock()
    mock_adapter.parse.return_value = []

    with patch("scheduler.runner._fetch", return_value=("<html></html>", 200)), \
         patch("scheduler.runner._load_adapter", return_value=mock_adapter), \
         patch("scheduler.runner._check_schema", return_value=False), \
         patch("adapters.addis_fortune.adapter.get_adapter_for_key", return_value=None):
        result = run_source(db, src_id)

    assert result["status"] == "failed"
    assert result["error_code"] == "zero_records_extracted"

    with db.cursor() as cur:
        cur.execute("SELECT status, error_code, records_found FROM collection_run WHERE source_id = %s", (src_id,))
        row = cur.fetchone()
        assert row[0] == "failed"
        assert row[1] == "zero_records_extracted"
        assert row[2] == 0


def test_inverted_category_spread_flagged_suspicious(db):
    bank_id = _make_bank(db, "INV1")
    src_id = _make_source(db, bank_id, "inv1")
    run_id = _make_run(db, src_id)

    rec_cash = _record(currency="USD", buying="160.00", selling="163.00", category="cash")
    rec_txn = _record(currency="USD", buying="163.00", selling="166.00", category="transactional")

    res = ingest(db, [rec_cash, rec_txn], src_id, run_id)
    assert res.suspicious is True


# ---------------------------------------------------------------------------
# P1 — Scheduler characterization tests
# ---------------------------------------------------------------------------

from scheduler.runner import Scheduler
from infrastructure.circuit_breaker import CircuitBreaker


def _make_scheduler_source(conn, code):
    """Seed a bank + source and return source_id."""
    bank_id = _make_bank(conn, code)
    src_id = _make_source(conn, bank_id, code.lower())
    conn.commit()
    return src_id


def test_scheduler_run_source_fallback_on_zero_records(db):
    """When the primary adapter returns 0 records, Scheduler calls _try_af_fallback
    and the result contains fallback='addis_fortune'."""
    src_id = _make_scheduler_source(db, "SCH1")

    mock_adapter = MagicMock()
    mock_adapter.parse.return_value = []

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_adapter

    af_result = {
        "source_id": src_id,
        "status": "success",
        "accepted": 1,
        "flagged": 0,
        "rejected": 0,
        "duplicates": 0,
        "fallback": "addis_fortune",
    }

    scheduler = Scheduler(adapter_registry=mock_registry)

    with patch("scheduler.runner._fetch", return_value=("<html>", 200)), \
         patch("scheduler.runner._check_schema", return_value=False), \
         patch("scheduler.runner._try_af_fallback", return_value=af_result) as mock_fallback, \
         patch("adapters.addis_fortune.adapter.get_adapter_for_key", return_value=None):
        result = scheduler.run_source(db, src_id)

    mock_fallback.assert_called_once()
    assert result.get("fallback") == "addis_fortune"


def test_scheduler_run_source_skipped_when_circuit_open(db):
    """When circuit_breaker.should_attempt returns False and no AF fallback exists,
    Scheduler.run_source returns status='skipped'."""
    src_id = _make_scheduler_source(db, "SCH2")

    mock_cb = MagicMock(spec=CircuitBreaker)
    mock_cb.should_attempt.return_value = False

    scheduler = Scheduler(circuit_breaker=mock_cb)

    with patch("scheduler.runner._try_af_fallback", return_value=None):
        result = scheduler.run_source(db, src_id)

    assert result["status"] == "skipped"
    assert result.get("detail") == "circuit breaker open"


def test_scheduler_run_source_records_failure_on_http_error(db):
    """When the HTTP fetch raises, Scheduler calls circuit_breaker.record_failure."""
    src_id = _make_scheduler_source(db, "SCH3")

    mock_cb = MagicMock(spec=CircuitBreaker)
    mock_cb.should_attempt.return_value = True

    mock_registry = MagicMock()
    mock_registry.get.side_effect = RuntimeError("HTTP fetch failed: connection refused")

    scheduler = Scheduler(adapter_registry=mock_registry, circuit_breaker=mock_cb)

    with patch("scheduler.runner._try_af_fallback", return_value=None):
        result = scheduler.run_source(db, src_id)

    mock_cb.record_failure.assert_called_once()
    assert result["status"] == "failed"
