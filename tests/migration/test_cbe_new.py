"""
Tests for CBE (Commercial Bank of Ethiopia) adapter migration.

Validates new adapter against golden snapshot from legacy adapter.
"""

import json
import pytest
from datetime import date
from pathlib import Path

from adapters.banks.cbe_new import ADAPTER
from adapters.core.contract import ParseContext


@pytest.fixture
def golden_data():
    """Load golden snapshot from legacy CBE adapter."""
    golden_file = Path(__file__).parent.parent.parent / "golden" / "cbe_api.json"
    with open(golden_file, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def parse_context():
    """Standard parse context for tests."""
    return ParseContext(
        category="cash",
        collection_date=date(2026, 11, 26),
        source_id=1,
    )


def test_cbe_adapter_key():
    """Verify adapter key matches."""
    assert ADAPTER.key == "cbe_api"


def test_cbe_parse_success(golden_data, parse_context):
    """Test successful parsing of CBE API response."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    assert len(outcome.records) > 0, "Should parse records"
    assert len(outcome.records) >= 3300, "Should have ~3300+ records"
    
    # Check record structure
    rec = outcome.records[0]
    assert hasattr(rec, 'source_currency_code')
    assert hasattr(rec, 'buying_rate')
    assert hasattr(rec, 'selling_rate')
    assert hasattr(rec, 'category')
    assert hasattr(rec, 'effective_date')


def test_cbe_currencies(golden_data, parse_context):
    """Test that major currencies are present."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    currencies = {r.source_currency_code for r in outcome.records}
    
    # Major currencies should be present
    expected = {"USD", "EUR", "GBP", "SAR", "AED", "CNY"}
    assert expected.issubset(currencies), f"Missing currencies: {expected - currencies}"


def test_cbe_categories(golden_data, parse_context):
    """Test that both cash and transactional categories are present."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    categories = {r.category for r in outcome.records}
    
    assert "cash" in categories, "Should have cash category"
    assert "transactional" in categories, "Should have transactional category"


def test_cbe_rates_valid(golden_data, parse_context):
    """Test that rates are valid decimals."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    # Most rates should be positive (allow some bad data from source)
    positive_count = 0
    negative_count = 0
    
    for rec in outcome.records[:100]:  # Check first 100
        if rec.buying_rate is not None:
            if rec.buying_rate > 0:
                positive_count += 1
            else:
                negative_count += 1
        if rec.selling_rate is not None:
            if rec.selling_rate > 0:
                positive_count += 1
            else:
                negative_count += 1
    
    # At least 95% should be positive (allowing for bad source data)
    assert positive_count > negative_count * 20, \
        f"Too many invalid rates: {positive_count} positive vs {negative_count} negative"


def test_cbe_dates_present(golden_data, parse_context):
    """Test that dates are parsed correctly."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    dated_records = [r for r in outcome.records if r.effective_date is not None]
    
    assert len(dated_records) > 3000, "Most records should have dates"
    
    # Check date format
    for rec in dated_records[:10]:
        assert isinstance(rec.effective_date, date), "Date should be date object"
        assert rec.effective_date_basis == "source_published", "Should use source date"


def test_cbe_empty_payload(parse_context):
    """Test handling of empty payload."""
    outcome = ADAPTER.parse("", parse_context)
    
    assert len(outcome.records) == 0
    assert len(outcome.issues) > 0
    assert any("JSON" in i.detail or "empty" in i.detail.lower() for i in outcome.issues)


def test_cbe_invalid_json(parse_context):
    """Test handling of invalid JSON."""
    outcome = ADAPTER.parse("{invalid json}", parse_context)
    
    assert len(outcome.records) == 0
    assert len(outcome.issues) > 0
    assert any("JSON" in i.detail for i in outcome.issues)


def test_cbe_empty_array(parse_context):
    """Test handling of empty JSON array."""
    outcome = ADAPTER.parse("[]", parse_context)
    
    assert len(outcome.records) == 0
    assert len(outcome.issues) > 0


def test_cbe_deterministic_output(golden_data, parse_context):
    """Test that parsing is deterministic (same input → same output)."""
    outcome1 = ADAPTER.parse(golden_data['payload'], parse_context)
    outcome2 = ADAPTER.parse(golden_data['payload'], parse_context)
    
    assert len(outcome1.records) == len(outcome2.records)
    
    # Check that records are in same order
    for r1, r2 in zip(outcome1.records[:10], outcome2.records[:10]):
        assert r1.source_currency_code == r2.source_currency_code
        assert r1.category == r2.category
        assert r1.buying_rate == r2.buying_rate
        assert r1.selling_rate == r2.selling_rate


def test_cbe_match_count(golden_data, parse_context):
    """Test that record count is close to legacy count."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    legacy_count = golden_data['record_count']
    new_count = len(outcome.records)
    
    # Allow small difference due to edge case handling
    diff = abs(new_count - legacy_count)
    assert diff <= 10, f"Record count diff too large: {diff} (legacy: {legacy_count}, new: {new_count})"
