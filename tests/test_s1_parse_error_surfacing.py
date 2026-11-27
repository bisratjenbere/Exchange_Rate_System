"""
Test that parse errors are properly surfaced through ParseOutcome.

Clean architecture - all adapters return ParseOutcome with structured issues.
Errors are captured in ParseOutcome.issues and formatted for storage.
"""

import pytest
from unittest.mock import Mock
from datetime import date
from decimal import Decimal

from scheduler.runner import _parse
from scheduler.extraction.recorder import _format_error_summary
from adapters.core.contract import ParseOutcome, ParseContext, RowIssue, Severity, IssueCode
from domain.records import AdapterRecord


def test_parse_returns_three_tuple():
    """_parse() returns (records, errors, warnings) from ParseOutcome."""
    mock_adapter = Mock()
    
    # Clean adapters return ParseOutcome
    mock_adapter.parse.return_value = ParseOutcome(
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
        issues=(
            RowIssue(
                row_ref="row_5",
                code="invalid_rate",
                detail="Invalid rate format",
                severity=Severity.ERROR,
            ),
        ),
        rows_seen=1,
        structure_hash=None,
    )
    
    records, errors, warnings = _parse(mock_adapter, "<html>test</html>", "cash")
    
    assert len(records) == 1
    assert len(errors) == 1
    assert len(warnings) == 0


def test_parse_with_warnings():
    """_parse() extracts warnings from ParseOutcome.issues."""
    mock_adapter = Mock()
    
    mock_adapter.parse.return_value = ParseOutcome(
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
        issues=(
            RowIssue(
                row_ref="page",
                code="stale_date",
                detail="Date is stale",
                severity=Severity.WARNING,
            ),
        ),
        rows_seen=1,
        structure_hash=None,
    )
    
    records, errors, warnings = _parse(mock_adapter, '{"rates":[]}', "cash")
    
    assert len(records) == 1
    assert len(errors) == 0
    assert len(warnings) == 1


def test_parse_with_no_issues():
    """_parse() handles successful parse with no issues."""
    mock_adapter = Mock()
    mock_adapter.parse.return_value = ParseOutcome(
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
            AdapterRecord(
                source_currency_code="EUR",
                quote_currency_code="ETB",
                effective_date=date.today(),
                effective_date_basis="collection_date_fallback",
                category="cash",
                buying_rate=Decimal("120.00"),
                selling_rate=Decimal("125.00"),
                source_rate_text="120.00/125.00",
            ),
        ),
        issues=tuple(),
        rows_seen=2,
        structure_hash=None,
    )
    
    records, errors, warnings = _parse(mock_adapter, '{"rates":[]}', "cash")
    
    assert len(records) == 2
    assert len(errors) == 0
    assert len(warnings) == 0


def test_format_error_summary_with_errors():
    """Error summary formatting includes error count and details."""
    errors = [
        "table_0:missing",
        "row_5:USD:invalid_rate",
        "row_12:EUR:buy_above_sell"
    ]
    warnings = []
    
    summary = _format_error_summary(errors, warnings, 20)
    
    assert "3 parse error(s)" in summary
    assert "table_0:missing" in summary
    assert "row_5:USD:invalid_rate" in summary
    assert len(summary) <= 500  # DB column limit


def test_format_error_summary_with_warnings():
    """Error summary includes warnings."""
    errors = []
    warnings = ["stale_date:2024-01-01", "unknown_currency:XXX"]
    
    summary = _format_error_summary(errors, warnings, 10)
    
    assert "2 warning(s)" in summary
    assert "stale_date:2024-01-01" in summary


def test_format_error_summary_empty():
    """Empty errors/warnings returns None."""
    summary = _format_error_summary([], [], 10)
    assert summary is None


def test_format_error_summary_truncates_long_errors():
    """Long error details are truncated to prevent DB overflow."""
    errors = ["x" * 200]  # Very long error
    warnings = []
    
    summary = _format_error_summary(errors, warnings, 1)
    
    assert len(summary) <= 500
    assert "1 parse error(s)" in summary


def test_fetch_result_includes_errors_and_warnings():
    """FetchResult dataclass includes errors and warnings fields."""
    from scheduler.extraction.fetcher import FetchResult
    
    result = FetchResult(
        records=[],
        raw_content="<html></html>",
        http_status=200,
        schema_changed=False,
        duration_ms=100,
        adapter_key="test",
        adapter=Mock(),
        errors=["error1"],
        warnings=["warning1"]
    )
    
    assert result.errors == ["error1"]
    assert result.warnings == ["warning1"]


def test_real_adapter_parse_errors_captured():
    """
    Integration test: Real adapter parse errors are captured.
    
    Uses dashen adapter with corrupt payload to generate real errors.
    """
    from infrastructure.adapter_registry_v2 import default_registry
    
    adapter = default_registry.get("dashen_html")
    
    # Corrupt HTML that will trigger parse errors
    corrupt_html = "<html><body>No table here</body></html>"
    
    records, errors, warnings = _parse(adapter, corrupt_html, "cash")
    
    # Dashen should report missing tables
    assert len(records) == 0
    assert len(errors) > 0
    error_str = " ".join(str(e) for e in errors)
    assert "missing" in error_str.lower() or "not found" in error_str.lower() or "expected" in error_str.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
