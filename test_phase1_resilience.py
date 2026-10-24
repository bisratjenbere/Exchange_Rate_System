#!/usr/bin/env python3
"""
Test Phase 1 resilience enhancements:
- Multi-strategy table detection
- Fuzzy CSS selectors
- Enhanced field detection patterns

Tests against existing fixtures to ensure backward compatibility
and improved resilience to variations.
"""
import sys
from pathlib import Path

# Test 1: Field Detection Pattern Enhancements
def test_enhanced_field_patterns():
    """Test that enhanced field patterns handle variations."""
    from field_detection.detector import FieldDetector
    
    detector = FieldDetector()
    
    test_cases = [
        # Original patterns (should still work)
        ({"buying": 160, "selling": 165}, 1, "Original generic"),
        ({"cashBuying": 160, "cashSelling": 165}, 1, "Original camelCase"),
        ({"cash_buying": 160, "cash_selling": 165}, 1, "Original underscore"),
        
        # New: Numbered variants
        ({"buying_1": 160, "selling_1": 165}, 1, "Numbered _1"),
        ({"buying_2": 160, "selling_2": 165}, 1, "Numbered _2"),
        ({"cash_buying_1": 160, "cash_selling_1": 165}, 1, "Cash numbered"),
        
        # New: Hyphenated
        ({"cash-buying": 160, "cash-selling": 165}, 1, "Hyphenated"),
        ({"buying-rate": 160, "selling-rate": 165}, 1, "Hyphenated rate"),
        
        # New: Abbreviated
        ({"buy_r": 160, "sell_r": 165}, 1, "Abbreviated _r"),
        ({"buy_rt": 160, "sell_rt": 165}, 1, "Abbreviated _rt"),
        ({"buyRate": 160, "sellRate": 165}, 1, "camelCase Rate"),
        
        # Multi-category detection
        ({"buying": 160, "selling": 165, "tra_buying": 161, "tra_selling": 166}, 2, "Multi-category"),
    ]
    
    passed = 0
    failed = 0
    
    for data, expected_pairs, description in test_cases:
        pairs = detector.detect_field_pairs(data)
        if len(pairs) == expected_pairs:
            print(f"✅ {description}: Found {len(pairs)} pair(s)")
            passed += 1
        else:
            print(f"❌ {description}: Expected {expected_pairs}, got {len(pairs)}")
            print(f"   Data: {data}")
            print(f"   Pairs: {pairs}")
            failed += 1
    
    print(f"\n📊 Field Pattern Tests: {passed} passed, {failed} failed")
    return failed == 0


# Test 2: Fuzzy Table Selection
def test_fuzzy_table_selection():
    """Test that fuzzy selectors find tables with various CSS classes."""
    from bs4 import BeautifulSoup
    from adapters.base import HTMLTableAdapter
    
    class TestAdapter(HTMLTableAdapter):
        def get_source_url(self): return "test"
        def get_adapter_key(self): return "test"
        def _process_tables(self, soup, tables, **kwargs):
            from adapters.base import ParseResult
            result = ParseResult()
            result.records = [f"table_{i}" for i in range(len(tables))]
            return result
    
    adapter = TestAdapter()
    
    test_cases = [
        # Exact match (original behavior)
        ('<table><tr><td>USD</td></tr></table>', 1, "Exact table"),
        
        # Fuzzy CSS class matches
        ('<table class="rate-table"><tr><td>USD</td></tr></table>', 1, "rate-table class"),
        ('<table class="exchange-rates"><tr><td>USD</td></tr></table>', 1, "exchange-rates class"),
        ('<table class="daily-rates-2024"><tr><td>USD</td></tr></table>', 1, "Versioned class"),
        
        # Table inside div with rate class
        ('<div class="exchange-container"><table><tr><td>USD</td></tr></table></div>', 1, "Table in div"),
        
        # Multiple tables
        ('<table class="rates"><tr><td>USD</td></tr></table><table class="rates"><tr><td>EUR</td></tr></table>', 2, "Multiple tables"),
    ]
    
    passed = 0
    failed = 0
    
    for html, expected_count, description in test_cases:
        soup = BeautifulSoup(html, "html.parser")
        tables, strategy = adapter._find_tables_resilient(soup)
        if len(tables) == expected_count:
            print(f"✅ {description}: Found {len(tables)} table(s) using '{strategy}'")
            passed += 1
        else:
            print(f"❌ {description}: Expected {expected_count}, got {len(tables)}")
            failed += 1
    
    print(f"\n📊 Fuzzy Selector Tests: {passed} passed, {failed} failed")
    return failed == 0


# Test 3: Backward Compatibility with Real Adapters
def test_real_adapter_backward_compatibility():
    """Test that enhancements don't break existing adapters."""
    from adapters.dashen.adapter import DashenAdapter
    from adapters.wegagen.adapter import WegagenAdapter
    
    print("\n🔍 Testing backward compatibility with real adapters...")
    
    # Test Dashen (HTML Table)
    try:
        dashen = DashenAdapter()
        fixture_path = Path("fixtures/dashen/normal.html")
        if fixture_path.exists():
            html = fixture_path.read_text()
            result = dashen.parse(html)
            if result.is_success() and len(result.records) > 0:
                print(f"✅ Dashen: Parsed {len(result.records)} records")
            else:
                print(f"❌ Dashen: Failed with errors: {result.errors}")
                return False
        else:
            print(f"⚠️  Dashen fixture not found, skipping")
    except Exception as e:
        print(f"❌ Dashen: Exception: {e}")
        return False
    
    # Test Wegagen (JSON API)
    try:
        wegagen = WegagenAdapter()
        # Test with a minimal valid Strapi envelope
        test_json = '''{
            "data": [
                {
                    "id": 1,
                    "attributes": {
                        "code": "USD",
                        "date": "2026-10-23",
                        "buying": 160.50,
                        "selling": 164.20,
                        "tra_buying": 161.00,
                        "tra_selling": 165.00
                    }
                }
            ]
        }'''
        result = wegagen.parse(test_json)
        if result.is_success() and len(result.records) > 0:
            print(f"✅ Wegagen: Parsed {len(result.records)} records")
        else:
            print(f"❌ Wegagen: Failed with errors: {result.errors}")
            return False
    except Exception as e:
        print(f"❌ Wegagen: Exception: {e}")
        return False
    
    return True


# Test 4: Resilience to Schema Variations
def test_schema_variations():
    """Test that system handles CSS class changes gracefully."""
    from adapters.base import HTMLTableAdapter, ParseResult
    from bs4 import BeautifulSoup
    
    class SimpleAdapter(HTMLTableAdapter):
        def get_source_url(self): return "test"
        def get_adapter_key(self): return "test"
        def _process_tables(self, soup, tables, **kwargs):
            result = ParseResult()
            # Just count tables
            for i, table in enumerate(tables):
                rows = table.find_all("tr")
                result.records.append(f"table_{i}_rows_{len(rows)}")
            return result
    
    adapter = SimpleAdapter()
    
    # Original HTML
    original = '''
    <table class="rates-table">
        <tr><td>USD</td><td>160</td><td>165</td></tr>
        <tr><td>EUR</td><td>180</td><td>185</td></tr>
    </table>
    '''
    
    # Variation 1: CSS class renamed
    renamed_class = '''
    <table class="exchange-rates-2024">
        <tr><td>USD</td><td>160</td><td>165</td></tr>
        <tr><td>EUR</td><td>180</td><td>185</td></tr>
    </table>
    '''
    
    # Variation 2: No class at all
    no_class = '''
    <table>
        <tr><td>USD</td><td>160</td><td>165</td></tr>
        <tr><td>EUR</td><td>180</td><td>185</td></tr>
    </table>
    '''
    
    test_cases = [
        (original, "Original HTML"),
        (renamed_class, "Renamed CSS class"),
        (no_class, "No CSS class"),
    ]
    
    passed = 0
    failed = 0
    
    for html, description in test_cases:
        try:
            result = adapter.parse(html)
            if result.is_success() and len(result.records) > 0:
                print(f"✅ {description}: Success ({len(result.records)} records)")
                passed += 1
            else:
                print(f"❌ {description}: Failed - {result.errors}")
                failed += 1
        except Exception as e:
            print(f"❌ {description}: Exception: {e}")
            failed += 1
    
    print(f"\n📊 Schema Variation Tests: {passed} passed, {failed} failed")
    return failed == 0


def main():
    """Run all Phase 1 resilience tests."""
    print("=" * 70)
    print("🚀 PHASE 1 RESILIENCE ENHANCEMENTS - TEST SUITE")
    print("=" * 70)
    
    results = []
    
    print("\n" + "=" * 70)
    print("TEST 1: Enhanced Field Detection Patterns")
    print("=" * 70)
    results.append(("Field Patterns", test_enhanced_field_patterns()))
    
    print("\n" + "=" * 70)
    print("TEST 2: Fuzzy Table Selection")
    print("=" * 70)
    results.append(("Fuzzy Selectors", test_fuzzy_table_selection()))
    
    print("\n" + "=" * 70)
    print("TEST 3: Backward Compatibility")
    print("=" * 70)
    results.append(("Backward Compat", test_real_adapter_backward_compatibility()))
    
    print("\n" + "=" * 70)
    print("TEST 4: Schema Variation Resilience")
    print("=" * 70)
    results.append(("Schema Variations", test_schema_variations()))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 FINAL SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 All Phase 1 enhancements working correctly!")
        print("✅ System is more resilient to schema changes")
        return 0
    else:
        print("\n⚠️  Some tests failed - review output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
