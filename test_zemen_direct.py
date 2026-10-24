#!/usr/bin/env python3
"""Direct test of Zemen adapter after field detection migration."""

import requests
from adapters.zemen.adapter import ZemenAdapter, FETCH_POST_DATA, FETCH_HEADERS

def test_zemen():
    print("=== Testing Zemen Adapter (After Field Detection Migration) ===\n")
    
    adapter = ZemenAdapter()
    print(f"Adapter key: {adapter.get_adapter_key()}")
    print(f"Source URL: {adapter.get_source_url()}")
    print(f"Field Config: {adapter.FIELD_CONFIG}")
    print()
    
    # Fetch using POST with action parameter
    print("Fetching raw content (POST with action=get_exchange_rates)...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        **FETCH_HEADERS
    }
    
    try:
        resp = requests.post(
            adapter.get_source_url(),
            data=FETCH_POST_DATA,
            headers=headers,
            timeout=15
        )
        print(f"HTTP Status: {resp.status_code}")
        print(f"Content length: {len(resp.text)} bytes\n")
        
        if resp.status_code != 200:
            print(f"❌ HTTP Error: {resp.status_code}")
            return
    except Exception as e:
        print(f"❌ FETCH FAILED: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Parse
    print("Parsing content...")
    try:
        result = adapter.parse(resp.text)
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
            expected_categories = {'transactional', 'cash', 'weighted_average'}
            found_categories = set(categories.keys())
            unexpected = found_categories - expected_categories
            if unexpected:
                print(f"\n⚠️  UNEXPECTED CATEGORIES: {unexpected}")
            
            missing = expected_categories - found_categories
            if missing:
                print(f"\n📝 Note: {missing} not found (may not be published)")
            
            # Check that UNKNOWN is not present
            if 'UNKNOWN' in categories:
                print(f"\n⚠️  Note: UNKNOWN category found ({categories['UNKNOWN']} records)")
                print(f"    This should be context-assigned to transactional or weighted_average")
            else:
                print(f"\n✓ UNKNOWN category correctly processed")
            
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
    test_zemen()
