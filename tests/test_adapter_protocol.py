"""
Tests for UniversalAdapter protocol (clean architecture only)
"""

import pytest
from datetime import date
from decimal import Decimal

from adapters.core.protocol import (
    UniversalAdapter,
    is_universal_adapter,
    validate_adapter,
)
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, Severity
from domain.records import AdapterRecord


class MockNewAdapter:
    """Mock adapter implementing UniversalAdapter protocol"""
    
    key = "mock_new"
    url = "https://example.com"
    fetch_kind = "http_get"
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """Parse and return outcome"""
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


def test_is_universal_adapter_validates_new_adapter():
    """Test that new adapter passes protocol check"""
    adapter = MockNewAdapter()
    assert is_universal_adapter(adapter)


def test_is_universal_adapter_rejects_invalid():
    """Test that invalid object fails protocol check"""
    
    class InvalidAdapter:
        pass
    
    assert not is_universal_adapter(InvalidAdapter())


def test_validate_adapter_accepts_valid():
    """Test validation of valid adapter"""
    adapter = MockNewAdapter()
    errors = validate_adapter(adapter)
    assert errors == []


def test_validate_adapter_detects_missing_key():
    """Test validation detects missing key"""
    
    class NoKey:
        url = "test"
        def parse(self, raw, ctx):
            pass
    
    errors = validate_adapter(NoKey())
    assert any("key" in err.lower() for err in errors)


def test_validate_adapter_detects_missing_url():
    """Test validation detects missing url"""
    
    class NoUrl:
        key = "test"
        def parse(self, raw, ctx):
            pass
    
    errors = validate_adapter(NoUrl())
    assert any("url" in err.lower() for err in errors)


def test_validate_adapter_detects_missing_parse():
    """Test validation detects missing parse method"""
    
    class NoParse:
        key = "test"
        url = "test"
    
    errors = validate_adapter(NoParse())
    assert any("parse" in err.lower() for err in errors)


def test_new_adapter_works_with_actual_import():
    """Test that actual clean adapters satisfy protocol"""
    try:
        from adapters.banks.cbe import ADAPTER
        assert is_universal_adapter(ADAPTER)
        errors = validate_adapter(ADAPTER)
        assert errors == []
    except ImportError:
        pytest.skip("CBE adapter not available")


def test_all_registered_adapters_satisfy_protocol():
    """Test that all 33 registered adapters satisfy the protocol"""
    try:
        from infrastructure.adapter_registry_v2 import default_registry
        
        for adapter_key in default_registry.list_keys():
            adapter = default_registry.get(adapter_key)
            assert is_universal_adapter(adapter), f"{adapter_key} should satisfy protocol"
            errors = validate_adapter(adapter)
            assert errors == [], f"{adapter_key} should have no validation errors: {errors}"
    except ImportError:
        pytest.skip("Registry not available")
