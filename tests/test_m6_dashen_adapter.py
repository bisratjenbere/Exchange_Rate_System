"""
Dashen Bank adapter tests (Type D — multi-table HTML).
All tests use fixtures — no network calls.
Fixtures: fixtures/dashen/{normal,empty,malformed,partial_one_table,no_date_in_weighted}.html
"""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from adapters.dashen.adapter import parse, schema_fingerprint, ADAPTER_KEY
from domain.enums import IdentityStatus
from pipeline.validate import validate, ValidationStatus
from pipeline.identity import build_identity
from pipeline.fingerprint import compute_fingerprint

FIXTURE_DIR = Path("fixtures/dashen")


def _load(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.html").read_text()


# ── normal fixture ────────────────────────────────────────────────────────────

def test_normal_returns_records_and_no_errors():
    records, errors = parse(_load("normal"))
    assert len(records) > 0
    assert errors == []


def test_normal_three_categories_present():
    records, _ = parse(_load("normal"))
    cats = {r.category for r in records}
    assert cats == {"transactional", "cash", "weighted_average"}


def test_normal_usd_transactional_values():
    records, _ = parse(_load("normal"))
    r = next(r for r in records if r.source_currency_code == "USD" and r.category == "transactional")
    assert r.buying_rate == Decimal("160.8707")
    assert r.selling_rate == Decimal("164.0881")


def test_normal_usd_cash_values():
    records, _ = parse(_load("normal"))
    r = next(r for r in records if r.source_currency_code == "USD" and r.category == "cash")
    assert r.buying_rate == Decimal("160.8707")
    assert r.selling_rate == Decimal("164.0881")


def test_normal_usd_weighted_values():
    records, _ = parse(_load("normal"))
    r = next(r for r in records if r.source_currency_code == "USD" and r.category == "weighted_average")
    assert r.buying_rate == Decimal("163.8186")
    assert r.selling_rate == Decimal("166.0636")


def test_normal_weighted_avg_date_parsed():
    """Weighted average table embeds date in header — must be parsed as source_published."""
    records, _ = parse(_load("normal"))
    wa = [r for r in records if r.category == "weighted_average"]
    for r in wa:
        assert r.effective_date == date(2026, 10, 9)
        assert r.effective_date_basis == "source_published"


def test_normal_transactional_cash_no_date():
    """Transactional and cash tables have no source-published date → collection_date_fallback."""
    records, _ = parse(_load("normal"))
    for r in records:
        if r.category in ("transactional", "cash"):
            assert r.effective_date is None
            assert r.effective_date_basis == "collection_date_fallback"


def test_normal_per_table_dates_not_shared():
    """Gap review test F: per-table dates preserved separately, never shared across tables."""
    records, _ = parse(_load("normal"))
    wa_dates = {r.effective_date for r in records if r.category == "weighted_average"}
    txn_dates = {r.effective_date for r in records if r.category == "transactional"}
    assert wa_dates == {date(2026, 10, 9)}
    assert txn_dates == {None}


def test_normal_transactional_identity_ambiguous():
    """Transactional/cash: fallback date → identity_status=ambiguous."""
    records, _ = parse(_load("normal"))
    for r in records:
        if r.category in ("transactional", "cash"):
            lkey, istatus = build_identity(r, source_id=1)
            assert istatus == IdentityStatus.AMBIGUOUS
            assert lkey is None


def test_normal_weighted_identity_confirmed():
    """Weighted average: source_published date (no stable ID) → identity_status=confirmed."""
    records, _ = parse(_load("normal"))
    for r in records:
        if r.category == "weighted_average":
            lkey, istatus = build_identity(r, source_id=1)
            assert istatus == IdentityStatus.CONFIRMED
            assert lkey is not None


def test_normal_currency_name_preserved():
    records, _ = parse(_load("normal"))
    usd = next(r for r in records if r.source_currency_code == "USD" and r.category == "transactional")
    assert usd.currency_name == "US Dollar"


def test_normal_source_rate_text_preserved():
    records, _ = parse(_load("normal"))
    usd = next(r for r in records if r.source_currency_code == "USD" and r.category == "transactional")
    assert "160.8707" in usd.source_rate_text


def test_normal_raw_excerpt_preserved():
    records, _ = parse(_load("normal"))
    usd = next(r for r in records if r.source_currency_code == "USD" and r.category == "transactional")
    assert usd.raw_excerpt is not None
    assert "buying" in usd.raw_excerpt


def test_normal_all_records_pass_validation():
    records, _ = parse(_load("normal"))
    for r in records:
        status, msgs = validate(r)
        assert status != ValidationStatus.REJECTED, (
            f"Rejected: {r.source_currency_code}/{r.category}: {msgs}"
        )


def test_normal_transactional_row_count():
    """9 currencies in transactional table."""
    records, _ = parse(_load("normal"))
    txn = [r for r in records if r.category == "transactional"]
    assert len(txn) == 9


def test_normal_cash_row_count():
    """7 currencies in cash table."""
    records, _ = parse(_load("normal"))
    cash = [r for r in records if r.category == "cash"]
    assert len(cash) == 7


def test_normal_weighted_row_count():
    """4 currencies in weighted average table (actual fixture: USD, EUR, SAR, AED)."""
    records, _ = parse(_load("normal"))
    wa = [r for r in records if r.category == "weighted_average"]
    assert len(wa) == 4


def test_normal_aed_in_transactional_cash_and_weighted():
    """AED appears in all three tables in the actual fixture."""
    records, _ = parse(_load("normal"))
    cats_for_aed = {r.category for r in records if r.source_currency_code == "AED"}
    assert cats_for_aed == {"transactional", "cash", "weighted_average"}


def test_normal_fingerprints_unique():
    records, _ = parse(_load("normal"))
    fps = [compute_fingerprint(r, source_id=1) for r in records]
    assert len(fps) == len(set(fps))


# ── acceptance test 9 analogue: partial failure ───────────────────────────────

def test_partial_one_table_returns_records_and_errors():
    """Acceptance test 9: one table present → parse it; missing tables recorded as errors."""
    records, errors = parse(_load("partial_one_table"))
    assert len(records) > 0
    # Two tables missing → two errors
    assert len(errors) == 2
    assert any("cash" in e for e in errors)
    assert any("weighted_average" in e for e in errors)


def test_partial_one_table_only_transactional_records():
    records, _ = parse(_load("partial_one_table"))
    cats = {r.category for r in records}
    assert cats == {"transactional"}


# ── empty fixture ─────────────────────────────────────────────────────────────

def test_empty_returns_no_records_with_errors():
    records, errors = parse(_load("empty"))
    assert records == []
    assert len(errors) == 3  # all three tables missing


# ── malformed fixture ─────────────────────────────────────────────────────────

def test_malformed_returns_no_records_with_errors():
    records, errors = parse(_load("malformed"))
    assert records == []
    assert len(errors) == 3


# ── no date in weighted avg header ───────────────────────────────────────────

def test_no_date_in_weighted_falls_back():
    """When weighted avg header has no date, effective_date_basis=collection_date_fallback."""
    records, errors = parse(_load("no_date_in_weighted"))
    wa = [r for r in records if r.category == "weighted_average"]
    assert len(wa) > 0
    for r in wa:
        assert r.effective_date is None
        assert r.effective_date_basis == "collection_date_fallback"
    assert errors == []


# ── duplicate fetch ───────────────────────────────────────────────────────────

def test_duplicate_fetch_same_fingerprints():
    records1, _ = parse(_load("normal"))
    records2, _ = parse(_load("normal"))
    fps1 = sorted(compute_fingerprint(r, 1) for r in records1)
    fps2 = sorted(compute_fingerprint(r, 1) for r in records2)
    assert fps1 == fps2


# ── schema fingerprint ────────────────────────────────────────────────────────

def test_schema_fingerprint_deterministic():
    raw = _load("normal")
    assert schema_fingerprint(raw) == schema_fingerprint(raw)


def test_schema_fingerprint_changes_on_table_count_change():
    assert schema_fingerprint(_load("normal")) != schema_fingerprint(_load("partial_one_table"))


def test_schema_fingerprint_empty_returns_hash():
    fp = schema_fingerprint(_load("empty"))
    assert len(fp) == 64


# ── adapter key ───────────────────────────────────────────────────────────────

def test_adapter_key():
    assert ADAPTER_KEY == "dashen_html"
