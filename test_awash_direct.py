#!/usr/bin/env python3
"""Direct test of Awash adapter after field detection migration."""

from adapters.awash.adapter import AwashAdapter, fetch_raw

def test_awash():
    print("=== Testing Awash Adapter (After Field Detection Migration) ===\n")
    
    adapter = AwashAdapter()
    print(f"Adapter key: {adapter.get_adapter_key()}")
    print(f"Source URL: {adapter.get_source_url()}")
    print(f"Field Config: {adapter.FIELD_CONFIG}")
    print()
    
    # Fetch using custom two-step fetch (nonce extraction)
    print("Fetching raw content (2-step: nonce extraction + AJAX)...")
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    try:
        raw_content, status_code = fetch_raw(
            source_url=adapter.get_source_url(),
            user_agent=user_agent,
            ssl_verify=True
        )
        print(f"HTTP Status: {status_code}")
        print(f"Content length: {len(raw_content)} bytes\n")
        
        if status_code != 200:
            print(f"❌ HTTP Error: {status_code}")
            return
    except Exception as e:
        print(f"❌ FETCH FAILED: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Parse
    print("Parsing content...")
    try:
        result = adapter.parse(raw_content)
        print(f"✓ Parse completed")
        print(f"  Records found: {len(result.records)}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Warnings: {len(result.warnings)}\n")
        
        if result.errors:
            print("ERRORS:")
            for err in result.errors:
                print(f"  - {err}")
            print()
        
        if result.warnings:
            print("WARNINGS:")
            for warn in result.warnings:
                print(f"  - {warn}")
            print()
        
        if result.records:
            # Group by currency
            by_currency = {}
            for rec in result.records:
                if rec.source_currency_code not in by_currency:
                    by_currency[rec.source_currency_code] = []
                by_currency[rec.source_currency_code].append(rec)
            
            print(f"✓ Found {len(by_currency)} currencies")
            print()
            
            # Show USD in detail
            if 'USD' in by_currency:
                print("USD RECORDS:")
                for rec in by_currency['USD']:
                    print(f"  {rec.category:20} Buy: {rec.buying_rate or 'N/A':>12} Sell: {rec.selling_rate or 'N/A':>12}")
                    print(f"    Effective: {rec.effective_date} ({rec.effective_date_basis})")
                print()
            
            # Show sample of other currencies
            print("OTHER CURRENCIES (first 3):")
            for curr in sorted(by_currency.keys())[:3]:
                if curr == 'USD':
                    continue
                print(f"  {curr}:")
                for rec in by_currency[curr]:
                    print(f"    {rec.category:20} Buy: {rec.buying_rate or 'N/A':>12}")
            
            # Category summary
            categories = {}
            for rec in result.records:
                categories[rec.category] = categories.get(rec.category, 0) + 1
            
            print(f"\nCATEGORY SUMMARY:")
            for cat, count in sorted(categories.items()):
                print(f"  {cat:20} {count} records")
            
            # Check expected categories
            expected_categories = {'transactional', 'weighted_average'}
            found_categories = set(categories.keys())
            unexpected = found_categories - expected_categories
            if unexpected:
                print(f"\n⚠️  UNEXPECTED CATEGORIES: {unexpected}")
            
            missing = expected_categories - found_categories
            if missing:
                print(f"\n📝 Note: {missing} not found (may not be published)")
            
            # Check that UNKNOWN is filtered
            if 'UNKNOWN' in categories:
                print(f"\n❌ ERROR: UNKNOWN category should be filtered!")
            else:
                print(f"\n✓ UNKNOWN category correctly filtered")
            
        else:
            print("❌ NO RECORDS EXTRACTED")
            
    except Exception as e:
        print(f"❌ PARSE FAILED: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "="*70)
    print("✅ MIGRATION TEST COMPLETE")
    print("="*70)

if __name__ == "__main__":
    test_awash()
