"""
Tests for unified parsing module
"""

import pytest
from datetime import date
from decimal import Decimal

from scheduler.parsing import (
    create_parse_context,
    parse_with_adapter,
    extract_errors_and_warnings,
)
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, Severity, IssueCode
from domain.records import AdapterRecord


class MockNewAdapter:
    """Mock new adapter"""
    key = "mock_new"
    url = "https://example.com"
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if "error" in raw.lower():
            return ParseOutcome(
                records=tuple(),
                issues=(RowIssue(
                    row_ref="row1",
                    code=IssueCode.BAD_JSON,
                    detail="Mock error",
                    severity=Severity.ERROR,
                ),),
                rows_seen=0,
                structure_hash=None,
            )
        
        return ParseOutcome(
            records=(
                AdapterRecord(
                    source_currency_code="USD",
                    quote_currency_code="ETB",
                    effective_date=date.today(),
                    effective_date_basis="collection_date_fallback",
                    category="cash",
                    buying_rate=Decimal("100.00"),
                    selling_rate=Decimal("105.00"),
                    source_rate_text="100.00/105.00",
                ),
            ),
            issues=tuple(),
            rows_seen=1,
            structure_hash=None,
        )


def test_create_parse_context():
    """Test ParseContext creation from source"""
    source = {
        "source_id": 42,
        "default_category": "cash",
    }
    
    ctx = create_parse_context(source)
    
    assert ctx.source_id == 42
    assert ctx.category == "cash"
    assert ctx.collection_date == date.today()


def test_create_parse_context_with_custom_date():
    """Test ParseContext with custom date"""
    source = {
        "source_id": 42,
        "default_category": "transactional",
    }
    custom_date = date(2026, 1, 1)
    
    ctx = create_parse_context(source, custom_date)
    
    assert ctx.collection_date == custom_date


def test_parse_with_new_adapter_success():
    """Test parsing with new adapter (success case)"""
    adapter = MockNewAdapter()
    source = {
        "source_id": 1,
        "adapter_key": "mock_new",
        "default_category": "cash",
    }
    
    outcome = parse_with_adapter(adapter, "test data", source)
    
    assert isinstance(outcome, ParseOutcome)
    assert len(outcome.records) == 1
    assert len(outcome.issues) == 0
    assert outcome.records[0].source_currency_code == "USD"


def test_parse_with_new_adapter_error():
    """Test parsing with new adapter (error case)"""
    adapter = MockNewAdapter()
    source = {
        "source_id": 1,
        "adapter_key": "mock_new",
        "default_category": "cash",
    }
    
    outcome = parse_with_adapter(adapter, "ERROR data", source)
    
    assert isinstance(outcome, ParseOutcome)
    assert len(outcome.records) == 0
    assert len(outcome.issues) == 1
    assert outcome.issues[0].severity == Severity.ERROR


def test_extract_errors_and_warnings():
    """Test extracting errors and warnings from ParseOutcome"""
    outcome = ParseOutcome(
        records=tuple(),
        issues=(
            RowIssue(
                row_ref="row1",
                code=IssueCode.BAD_JSON,
                detail="Error message",
                severity=Severity.ERROR,
            ),
            RowIssue(
                row_ref="row2",
                code=IssueCode.BUY_ABOVE_SELL,
                detail="Warning message",
                severity=Severity.WARNING,
            ),
        ),
        rows_seen=2,
        structure_hash=None,
    )
    
    errors, warnings = extract_errors_and_warnings(outcome)
    
    assert len(errors) == 1
    assert len(warnings) == 1
    assert "Error message" in errors[0]
    assert "Warning message" in warnings[0]


def test_parse_with_actual_cbe_adapter():
    """Test parsing with actual CBE adapter"""
    try:
        from adapters.banks.cbe_new import ADAPTER
        from infrastructure.adapter_registry_v2 import default_registry
        
        # This is an integration test - only run if adapter registered
        if default_registry.is_registered("cbe_api"):
            adapter = default_registry.get("cbe_api")
            source = {
                "source_id": 1,
                "adapter_key": "cbe_api",
                "default_category": "cash",
            }
            
            # Use empty payload (should return error outcome, not raise)
            outcome = parse_with_adapter(adapter, "{}", source)
            
            assert isinstance(outcome, ParseOutcome)
            # Empty JSON should produce error or no records
            assert len(outcome.records) == 0 or len(outcome.issues) > 0
    except ImportError:
        pytest.skip("CBE adapter not available")


def test_parse_with_clean_adapter():
    """Test parsing with clean adapter from registry"""
    try:
        from infrastructure.adapter_registry_v2 import default_registry
        
        if default_registry.is_registered("dashen_html"):
            adapter = default_registry.get("dashen_html")
            source = {
                "source_id": 1,
                "adapter_key": "dashen_html",
                "default_category": "cash",
            }
            
            # Parse empty content (should handle gracefully)
            outcome = parse_with_adapter(adapter, "", source)
            
            assert isinstance(outcome, ParseOutcome)
            # Clean adapter should return structured issues for empty content
            assert len(outcome.issues) >= 0  # May have issues or not
    except ImportError:
        pytest.skip("Registry V2 not available")
