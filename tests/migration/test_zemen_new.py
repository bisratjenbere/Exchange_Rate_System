"""
Migration tests for Zemen Bank adapter (zemen_ajax).

Validates that the new zemen_new.py adapter produces identical results
to the legacy zemen_ajax adapter using golden snapshot.
"""

import json
import pytest
from pathlib import Path
from datetime import date

from adapters.banks.zemen_new import ADAPTER
from adapters.core.contract import ParseContext

# Path to golden snapshot
GOLDEN_PATH = Path(__file__).parent.parent.parent / "golden" / "zemen_ajax.json"


@pytest.fixture
def golden_data():
    """Load golden snapshot from legacy adapter."""
    with open(GOLDEN_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def parse_context():
    """Standard parse context for tests."""
    return ParseContext(
        category="cash",
        collection_date=date(2026, 11, 26),
        source_id=29,
    )


def test_golden_snapshot_exists():
    """Verify golden snapshot file exists."""
    assert GOLDEN_PATH.exists(), f"Golden snapshot not found: {GOLDEN_PATH}"


def test_adapter_key():
    """Test adapter key matches."""
    assert ADAPTER.key == "zemen_ajax"


def test_parse_success(golden_data, parse_context):
    """Test successful parsing of Zemen API response."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    assert len(outcome.records) > 0, "Should parse records"
    assert len(outcome.records) == 19, f"Should have 19 records, got {len(outcome.records)}"
    
    # Check record structure
    rec = outcome.records[0]
    assert hasattr(rec, 'source_currency_code')
    assert hasattr(rec, 'buying_rate')
    assert hasattr(rec, 'selling_rate')
    assert hasattr(rec, 'category')


def test_currencies_present(golden_data, parse_context):
    """Test that expected currencies are present."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    currencies = {r.source_currency_code for r in outcome.records}
    
    # Major currencies should be present
    expected = {"USD", "EUR", "GBP"}
    assert expected.issubset(currencies), f"Missing currencies: {expected - currencies}"


def test_both_categories_present(golden_data, parse_context):
    """Test that both cash and transactional categories are present."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    categories = {r.category for r in outcome.records}
    
    # Both should be present (Zemen provides both)
    assert "cash" in categories, "Should have cash category"
    assert "transactional" in categories or "day" in categories, "Should have transactional/day category"


def test_rates_valid(golden_data, parse_context):
    """Test that rates are valid decimals and positive (allowing some null rates from source)."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    valid_records = 0
    null_records = 0
    
    for rec in outcome.records:
        if rec.buying_rate is not None and rec.selling_rate is not None:
            assert rec.buying_rate > 0, f"{rec.source_currency_code} buying rate must be positive"
            assert rec.selling_rate > 0, f"{rec.source_currency_code} selling rate must be positive"
            valid_records += 1
        else:
            null_records += 1
    
    # Most records should have valid rates
    assert valid_records > null_records, \
        f"Too many invalid rates: {valid_records} valid vs {null_records} null"


def test_buy_less_than_sell(golden_data, parse_context):
    """Test that buying < selling for all rates (skipping null rates)."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    for rec in outcome.records:
        # Skip records with null rates (from source data)
        if rec.buying_rate is not None and rec.selling_rate is not None:
            assert rec.buying_rate < rec.selling_rate, \
                f"{rec.source_currency_code}: buying ({rec.buying_rate}) must be < selling ({rec.selling_rate})"


def test_record_count_matches_legacy(golden_data, parse_context):
    """Test that new adapter produces same record count as legacy."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    legacy_records = golden_data['records']
    
    assert len(outcome.records) == len(legacy_records), \
        f"Record count mismatch: new={len(outcome.records)}, legacy={len(legacy_records)}"


def test_currencies_match_legacy(golden_data, parse_context):
    """Test that currencies match legacy adapter."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    legacy_records = golden_data['records']
    
    new_currencies = {r.source_currency_code for r in outcome.records}
    legacy_currencies = {r['currency'] for r in legacy_records}
    
    assert new_currencies == legacy_currencies, \
        f"Currency mismatch: new={new_currencies}, legacy={legacy_currencies}"


def test_no_issues_reported(golden_data, parse_context):
    """Test that parsing produces no issues."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    assert len(outcome.issues) == 0, f"Should have no issues, got: {outcome.issues}"


def test_empty_response_handling(parse_context):
    """Test adapter handles empty response gracefully."""
    outcome = ADAPTER.parse("", parse_context)
    assert len(outcome.records) == 0
    # Should have an issue reported
    assert len(outcome.issues) > 0


def test_invalid_json_handling(parse_context):
    """Test adapter handles invalid JSON gracefully."""
    invalid_json = '{"data": [invalid json}'
    outcome = ADAPTER.parse(invalid_json, parse_context)
    assert len(outcome.records) == 0
    # Should have an issue reported
    assert len(outcome.issues) > 0
