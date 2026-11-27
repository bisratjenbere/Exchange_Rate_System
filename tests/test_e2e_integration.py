"""
End-to-end integration tests for scheduler with new architecture.

Tests the complete flow:
1. Load adapter from registry
2. Fetch content (mocked)
3. Parse with adapter
4. Validate ParseOutcome
5. Check backward compatibility
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from infrastructure.adapter_registry_v2 import default_registry
from scheduler.parsing import parse_with_adapter
from scheduler.extraction.fetcher import FetchResult
from adapters.core.contract import ParseOutcome, Severity
from domain.source import RateSource


def _src(source_id=1, adapter_key="cbe_api", default_category="cash") -> RateSource:
    return RateSource(
        id=source_id,
        adapter_key=adapter_key,
        source_url="https://example.com",
        ssl_verify=True,
        is_enabled=True,
        default_category=default_category,
    )


class TestNewAdaptersE2E:
    def test_cbe_adapter_registered(self):
        assert default_registry.is_registered("cbe_api")
        adapter = default_registry.get("cbe_api")
        assert adapter is not None
        assert adapter.key == "cbe_api"
    
    def test_zemen_adapter_registered(self):
        """Test Zemen adapter is registered and accessible"""
        assert default_registry.is_registered("zemen_ajax")
        adapter = default_registry.get("zemen_ajax")
        assert adapter is not None
        assert adapter.key == "zemen_ajax"
    
    def test_wegagen_adapter_registered(self):
        """Test Wegagen adapter is registered and accessible"""
        assert default_registry.is_registered("wegagen_api")
        adapter = default_registry.get("wegagen_api")
        assert adapter is not None
        assert adapter.key == "wegagen_api"
    
    def test_cbe_parse_with_golden_data(self):
        """Test CBE adapter with golden snapshot data"""
        import json
        from pathlib import Path
        
        golden_file = Path(__file__).parent.parent / "golden" / "cbe_api.json"
        if not golden_file.exists():
            pytest.skip("CBE golden file not available")
        
        with open(golden_file) as f:
            golden = json.load(f)
        
        adapter = default_registry.get("cbe_api")
        source = _src(source_id=1, adapter_key="cbe_api")
        outcome = parse_with_adapter(adapter, golden["payload"], source)
        
        assert isinstance(outcome, ParseOutcome)
        assert len(outcome.records) > 0
        assert len(outcome.records) >= 3300  # CBE has ~3400 records
        
        # Validate record structure
        rec = outcome.records[0]
        assert rec.source_currency_code is not None
        assert rec.buying_rate is not None
        assert rec.selling_rate is not None
    
    def test_zemen_parse_with_golden_data(self):
        """Test Zemen adapter with golden snapshot data"""
        import json
        from pathlib import Path
        
        golden_file = Path(__file__).parent.parent / "golden" / "zemen_ajax.json"
        if not golden_file.exists():
            pytest.skip("Zemen golden file not available")
        
        with open(golden_file) as f:
            golden = json.load(f)
        
        adapter = default_registry.get("zemen_ajax")
        source = _src(source_id=29, adapter_key="zemen_ajax")
        outcome = parse_with_adapter(adapter, golden["payload"], source)
        
        assert isinstance(outcome, ParseOutcome)
        assert len(outcome.records) == 19
        assert len(outcome.issues) == 0  # No errors expected
    
    def test_wegagen_parse_with_golden_data(self):
        """Test Wegagen adapter with golden snapshot data"""
        import json
        from pathlib import Path
        
        golden_file = Path(__file__).parent.parent / "golden" / "wegagen_api.json"
        if not golden_file.exists():
            pytest.skip("Wegagen golden file not available")
        
        with open(golden_file) as f:
            golden = json.load(f)
        
        adapter = default_registry.get("wegagen_api")
        source = _src(source_id=27, adapter_key="wegagen_api")
        outcome = parse_with_adapter(adapter, golden["payload"], source)
        
        assert isinstance(outcome, ParseOutcome)
        assert len(outcome.records) == 20
        assert len(outcome.issues) == 0


class TestLegacyAdaptersE2E:
    """End-to-end tests for legacy wrapped adapters"""
    
    def test_legacy_adapters_wrapped(self):
        """Test that legacy adapters are wrapped correctly"""
        # 0 legacy adapters remain - ALL CLEAN! 🎉
        legacy_adapters = []
        
        # Verify no legacy adapters exist - all are clean
        stats = default_registry.get_stats()
        assert stats['clean'] == 33, "Expected all 33 adapters to be clean"
        assert stats['total'] == 33, "Expected 33 total adapters"
    
    def test_legacy_adapter_parse_returns_outcome(self):
        """Test that all adapters return ParseOutcome (no legacy wrappers)"""
        # With 0 legacy adapters, test a clean adapter instead
        adapter = default_registry.get("cbe_api")
        source = _src(source_id=1, adapter_key="cbe_api")
        outcome = parse_with_adapter(adapter, "", source)
        
        assert isinstance(outcome, ParseOutcome)
        # Should have error issue
        assert len(outcome.issues) > 0

class TestBackwardCompatibility:
    """Test backward compatibility with legacy code"""
    
    def test_fetch_result_has_legacy_fields(self):
        """Test FetchResult maintains legacy fields"""
        from scheduler.extraction.fetcher import FetchResult
        from adapters.core.contract import ParseOutcome
        
        outcome = ParseOutcome(
            records=tuple(),
            issues=tuple(),
            rows_seen=0,
            structure_hash=None,
        )
        
        result = FetchResult(
            records=[],
            raw_content="test",
            http_status=200,
            schema_changed=False,
            duration_ms=100,
            adapter_key="test",
            adapter=None,
            errors=[],
            warnings=[],
            parse_outcome=outcome,
        )
        
        # Legacy fields should exist
        assert hasattr(result, 'records')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'warnings')
        # New field should exist
        assert hasattr(result, 'parse_outcome')
        assert result.parse_outcome is outcome
    
    def test_extract_errors_and_warnings(self):
        """Test extraction of errors/warnings for legacy code"""
        from scheduler.parsing import extract_errors_and_warnings
        from adapters.core.contract import RowIssue, Severity, IssueCode
        
        outcome = ParseOutcome(
            records=tuple(),
            issues=(
                RowIssue(
                    row_ref="row1",
                    code=IssueCode.BAD_JSON,
                    detail="Error detail",
                    severity=Severity.ERROR,
                ),
                RowIssue(
                    row_ref="row2",
                    code=IssueCode.BUY_ABOVE_SELL,
                    detail="Warning detail",
                    severity=Severity.WARNING,
                ),
            ),
            rows_seen=2,
            structure_hash=None,
        )
        
        errors, warnings = extract_errors_and_warnings(outcome)
        assert len(errors) == 1
        assert len(warnings) == 1
        assert "Error detail" in errors[0]
        assert "Warning detail" in warnings[0]


class TestErrorHandling:
    """Test error handling in new architecture"""
    
    def test_malformed_json_produces_issues(self):
        """Test malformed JSON produces structured issues"""
        adapter = default_registry.get("cbe_api")
        source = _src(source_id=1, adapter_key="cbe_api")
        outcome = parse_with_adapter(adapter, "invalid json{", source)
        
        assert isinstance(outcome, ParseOutcome)
        assert len(outcome.records) == 0
        assert len(outcome.issues) > 0
        assert outcome.issues[0].severity == Severity.ERROR
    
    def test_empty_content_handled_gracefully(self):
        """Test empty content is handled gracefully"""
        adapter = default_registry.get("cbe_api")
        source = _src(source_id=1, adapter_key="cbe_api")
        outcome = parse_with_adapter(adapter, "", source)
        
        assert isinstance(outcome, ParseOutcome)
        assert len(outcome.records) == 0
        # May or may not have issues depending on adapter


class TestPerformance:
    def test_cbe_parse_performance(self):
        """Test CBE parsing completes in reasonable time"""
        import json
        import time
        from pathlib import Path
        
        golden_file = Path(__file__).parent.parent / "golden" / "cbe_api.json"
        if not golden_file.exists():
            pytest.skip("CBE golden file not available")
        
        with open(golden_file) as f:
            golden = json.load(f)
        
        adapter = default_registry.get("cbe_api")
        source = _src(source_id=1, adapter_key="cbe_api")
        start = time.time()
        outcome = parse_with_adapter(adapter, golden["payload"], source)
        duration = time.time() - start
        
        assert duration < 1.0  # Should complete in under 1 second
        assert len(outcome.records) > 3000
    
    def test_registry_lookup_performance(self):
        """Test registry lookups are fast"""
        import time
        
        start = time.time()
        for _ in range(1000):
            adapter = default_registry.get("cbe_api")
        duration = time.time() - start
        
        assert duration < 0.1  # 1000 lookups in under 100ms


class TestRegistryStats:
    """Test registry statistics and introspection"""
    
    def test_registry_stats(self):
        """Test registry provides accurate stats"""
        stats = default_registry.get_stats()
        
        assert stats['total'] == 33
        assert stats['clean'] == 33  # 33 clean adapters - 100% CLEAN! 🎉
        assert stats['migration_progress'] == "33/33"
    
    def test_all_adapters_accessible(self):
        """Test all 32 adapters are accessible"""
        all_keys = default_registry.list_keys()
        
        assert len(all_keys) == 33
        
        # Test a few key adapters
        for key in ["cbe_api", "zemen_ajax", "wegagen_api", "dashen_html"]:
            assert key in all_keys
            adapter = default_registry.get(key)
            assert adapter is not None
