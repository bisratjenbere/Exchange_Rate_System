"""
CBE adapter tests (Commercial Bank of Ethiopia — Type A).
All tests use fixtures — no network calls.
Fixtures: fixtures/cbe/{normal,single_date,empty,malformed,schema_changed,unknown_currency}.json
"""
import json
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from adapters.cbe.adapter import parse, schema_fingerprint, ADAPTER_KEY
from domain.enums import IdentityStatus
from pipeline.validate import validate, ValidationStatus
from pipeline.identity import build_identity
from pipeline.fingerprint import compute_fingerprint

FIXTURE_DIR = Path("fixtures/cbe")


def _load(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.json").read_text()


# ── normal fixture ────────────────────────────────────────────────────────────

def test_normal_returns_list():
    records = parse(_load("normal"))
    assert isinstance(records, list)
    assert len(records) > 0


def test_normal_two_publications_two_categories_per_currency():
    """2 publication records × 20 currencies × up to 2 categories each."""
    records = parse(_load("normal"))
    # At minimum we get some records; exact count depends on zeros
    assert len(records) > 0
    categories = {r.category for r in records}
    assert categories <= {"cash", "transactional"}


def test_normal_no_weighted_average():
    """CBE API has no weighted average fields."""
    records = parse(_load("normal"))
    assert all(r.category != "weighted_average" for r in records)


def test_normal_usd_cash_values():
    records = parse(_load("single_date"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"]
    assert len(usd_cash) == 1
    r = usd_cash[0]
    assert r.buying_rate == Decimal("41.94899999")
    assert r.selling_rate == Decimal("42.78")


def test_normal_usd_transactional_values():
    records = parse(_load("single_date"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"]
    assert len(usd_txn) == 1
    r = usd_txn[0]
    assert r.buying_rate == Decimal("41.94")
    assert r.selling_rate == Decimal("42.78")


def test_normal_zero_becomes_none():
    """Zero rate → None (not offered). Confirmed pattern across 1205 zeros."""
    records = parse(_load("single_date"))
    # All rates that are not None must be positive
    for r in records:
        if r.buying_rate is not None:
            assert r.buying_rate > 0
        if r.selling_rate is not None:
            assert r.selling_rate > 0


def test_normal_both_zero_category_skipped():
    """If both sides of a category are zero → skip that record entirely."""
    records = parse(_load("single_date"))
    # No record should have both buying_rate and selling_rate as None
    # (that would mean both were zero and the record should have been skipped)
    for r in records:
        assert not (r.buying_rate is None and r.selling_rate is None)


def test_normal_effective_date_source_published():
    records = parse(_load("single_date"))
    for r in records:
        assert r.effective_date == date(2021, 4, 29)
        assert r.effective_date_basis == "source_published"


def test_normal_source_publication_key_set():
    records = parse(_load("single_date"))
    for r in records:
        assert r.source_publication_key == "609278320e47d52aafd34f23"


def test_normal_source_record_key_includes_category():
    """source_record_key = item_id:category for uniqueness across cash/transactional."""
    records = parse(_load("single_date"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"][0]
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"][0]
    assert usd_cash.source_record_key != usd_txn.source_record_key
    assert ":cash" in usd_cash.source_record_key
    assert ":transactional" in usd_txn.source_record_key


def test_normal_identity_confirmed():
    """CBE has stable ObjectID + source_published date → identity_status=confirmed."""
    records = parse(_load("single_date"))
    for r in records:
        lkey, istatus = build_identity(r, source_id=1)
        assert istatus == IdentityStatus.CONFIRMED
        assert lkey is not None


def test_normal_currency_name_preserved():
    records = parse(_load("single_date"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.currency_name == "US DOLLAR"


def test_normal_source_rate_text_preserved():
    records = parse(_load("single_date"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"][0]
    assert usd_cash.source_rate_text is not None
    assert "41.94899999" in usd_cash.source_rate_text


def test_normal_raw_excerpt_preserved():
    records = parse(_load("single_date"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"][0]
    assert usd_cash.raw_excerpt is not None
    assert "cashBuying" in usd_cash.raw_excerpt


def test_normal_all_records_pass_validation():
    records = parse(_load("single_date"))
    for r in records:
        status, msgs = validate(r)
        assert status != ValidationStatus.REJECTED, (
            f"Rejected: {r.source_currency_code}/{r.category}: {msgs}"
        )


def test_normal_fingerprints_unique_per_record():
    records = parse(_load("single_date"))
    fps = [compute_fingerprint(r, source_id=1) for r in records]
    assert len(fps) == len(set(fps)), "Duplicate fingerprints found"


def test_normal_two_dates_produce_distinct_logical_keys():
    """Two publication records for different dates → distinct logical keys."""
    records = parse(_load("normal"))
    lkeys = set()
    for r in records:
        lkey, _ = build_identity(r, source_id=1)
        assert lkey is not None
        lkeys.add(lkey)
    # 2 dates × currencies × categories → many distinct keys
    assert len(lkeys) > 20


def test_normal_cash_and_transactional_distinct_keys():
    """Acceptance test 2: cash and transactional same currency/date → distinct logical keys."""
    records = parse(_load("single_date"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"][0]
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"][0]
    lkey_cash, _ = build_identity(usd_cash, source_id=1)
    lkey_txn, _ = build_identity(usd_txn, source_id=1)
    assert lkey_cash != lkey_txn


# ── empty fixture ─────────────────────────────────────────────────────────────

def test_empty_returns_empty_list():
    records = parse(_load("empty"))
    assert records == []


# ── malformed fixture ─────────────────────────────────────────────────────────

def test_malformed_raises_value_error():
    """HTTP 200 with error body (not a JSON array) → ValueError."""
    with pytest.raises(ValueError, match="expected JSON array"):
        parse(_load("malformed"))


def test_malformed_json_raises_value_error():
    with pytest.raises(ValueError, match="JSON parse error"):
        parse("not json {{{")


# ── schema changed fixture ────────────────────────────────────────────────────

def test_schema_changed_raises_value_error():
    """Missing cashBuying field → ValueError (schema change detected)."""
    with pytest.raises(ValueError, match="missing"):
        parse(_load("schema_changed"))


# ── unknown currency fixture ──────────────────────────────────────────────────

def test_unknown_currency_passes_through():
    """Unknown currency code passes through — pipeline validates, not adapter."""
    records = parse(_load("unknown_currency"))
    xyz = [r for r in records if r.source_currency_code == "XYZ"]
    assert len(xyz) > 0


def test_unknown_currency_not_rejected_by_adapter():
    records = parse(_load("unknown_currency"))
    xyz = [r for r in records if r.source_currency_code == "XYZ"][0]
    status, _ = validate(xyz)
    assert status != ValidationStatus.REJECTED


# ── duplicate fetch ───────────────────────────────────────────────────────────

def test_duplicate_fetch_same_fingerprints():
    """Same data parsed twice → identical fingerprints → deduplication will skip."""
    records1 = parse(_load("single_date"))
    records2 = parse(_load("single_date"))
    fps1 = sorted(compute_fingerprint(r, 1) for r in records1)
    fps2 = sorted(compute_fingerprint(r, 1) for r in records2)
    assert fps1 == fps2


# ── schema fingerprint ────────────────────────────────────────────────────────

def test_schema_fingerprint_deterministic():
    raw = _load("normal")
    assert schema_fingerprint(raw) == schema_fingerprint(raw)


def test_schema_fingerprint_changes_on_new_field():
    data = json.loads(_load("normal"))
    data[0]["newField"] = "value"
    assert schema_fingerprint(_load("normal")) != schema_fingerprint(json.dumps(data))


def test_schema_fingerprint_stable_on_value_change():
    data = json.loads(_load("normal"))
    data[0]["ExchangeRate"][0]["cashBuying"] = 999.0
    assert schema_fingerprint(_load("normal")) == schema_fingerprint(json.dumps(data))


def test_schema_fingerprint_empty_returns_hash():
    fp = schema_fingerprint(_load("empty"))
    assert len(fp) == 64


# ── adapter key ───────────────────────────────────────────────────────────────

def test_adapter_key():
    assert ADAPTER_KEY == "cbe_api"
