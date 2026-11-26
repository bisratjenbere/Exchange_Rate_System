"""
Migration tests for Wegagen Bank adapter (wegagen_api).

Validates that the new wegagen_new.py adapter correctly parses
Strapi v4 API responses from Wegagen Bank.
"""

import json
import pytest
from pathlib import Path
from datetime import date

from adapters.banks.wegagen_new import ADAPTER
from adapters.core.contract import ParseContext

# Path to golden snapshot
GOLDEN_PATH = Path(__file__).parent.parent.parent / "golden" / "wegagen_api.json"


@pytest.fixture
def golden_data():
    """Load golden snapshot."""
    with open(GOLDEN_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def parse_context():
    """Standard parse context for tests."""
    return ParseContext(
        category="cash",
        collection_date=date(2026, 11, 26),
        source_id=27,
    )


def test_golden_snapshot_exists():
    """Verify golden snapshot file exists."""
    assert GOLDEN_PATH.exists(), f"Golden snapshot not found: {GOLDEN_PATH}"


def test_adapter_key():
    """Test adapter key matches."""
    assert ADAPTER.key == "wegagen_api"


def test_parse_success(golden_data, parse_context):
    """Test successful parsing of Wegagen API response."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    assert len(outcome.records) > 0, "Should parse records"
    assert len(outcome.records) == 20, f"Should have 20 records (10 currencies × 2 categories), got {len(outcome.records)}"
    
    # Check record structure
    rec = outcome.records[0]
    assert hasattr(rec, 'source_currency_code')
    assert hasattr(rec, 'buying_rate')
    assert hasattr(rec, 'selling_rate')
    assert hasattr(rec, 'category')
    assert hasattr(rec, 'effective_date')


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
    
    assert "cash" in categories, "Should have cash category"
    assert "transactional" in categories, "Should have transactional category"


def test_rates_valid(golden_data, parse_context):
    """Test that rates are valid decimals and positive."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    for rec in outcome.records:
        assert rec.buying_rate is not None, f"{rec.source_currency_code} has no buying rate"
        assert rec.selling_rate is not None, f"{rec.source_currency_code} has no selling rate"
        assert rec.buying_rate > 0, f"{rec.source_currency_code} buying rate must be positive"
        assert rec.selling_rate > 0, f"{rec.source_currency_code} selling rate must be positive"


def test_buy_less_than_sell(golden_data, parse_context):
    """Test that buying < selling for all rates."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    for rec in outcome.records:
        assert rec.buying_rate < rec.selling_rate, \
            f"{rec.source_currency_code}: buying ({rec.buying_rate}) must be < selling ({rec.selling_rate})"


def test_adr_011_cash_equals_transactional(golden_data, parse_context):
    """Test ADR-011: buying==tra_buying for all records."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    # Group by currency
    by_currency = {}
    for rec in outcome.records:
        if rec.source_currency_code not in by_currency:
            by_currency[rec.source_currency_code] = {}
        by_currency[rec.source_currency_code][rec.category] = (rec.buying_rate, rec.selling_rate)
    
    # Check that cash and transactional rates are equal (ADR-011)
    for currency, cats in by_currency.items():
        if "cash" in cats and "transactional" in cats:
            cash_buy, cash_sell = cats["cash"]
            tra_buy, tra_sell = cats["transactional"]
            assert cash_buy == tra_buy, \
                f"{currency}: cash buying ({cash_buy}) != transactional buying ({tra_buy}) [violates ADR-011]"
            assert cash_sell == tra_sell, \
                f"{currency}: cash selling ({cash_sell}) != transactional selling ({tra_sell}) [violates ADR-011]"


def test_dates_present(golden_data, parse_context):
    """Test that effective dates are parsed."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    dated_records = [r for r in outcome.records if r.effective_date is not None]
    
    # All records should have dates
    assert len(dated_records) == len(outcome.records), "All records should have effective dates"


def test_no_issues_reported(golden_data, parse_context):
    """Test that parsing produces no issues."""
    outcome = ADAPTER.parse(golden_data['payload'], parse_context)
    
    assert len(outcome.issues) == 0, f"Should have no issues, got: {outcome.issues}"


def test_empty_response_handling(parse_context):
    """Test adapter handles empty response gracefully."""
    outcome = ADAPTER.parse("", parse_context)
    assert len(outcome.records) == 0
    assert len(outcome.issues) > 0


def test_invalid_json_handling(parse_context):
    """Test adapter handles invalid JSON gracefully."""
    invalid_json = '{"data": [invalid json}'
    outcome = ADAPTER.parse(invalid_json, parse_context)
    assert len(outcome.records) == 0
    assert len(outcome.issues) > 0


def test_missing_data_key(parse_context):
    """Test adapter handles missing 'data' key."""
    invalid = json.dumps({"wrong_key": []})
    outcome = ADAPTER.parse(invalid, parse_context)
    assert len(outcome.records) == 0
    assert len(outcome.issues) > 0
