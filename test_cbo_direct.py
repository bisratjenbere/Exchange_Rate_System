#!/usr/bin/env python3
"""Direct test of CBO (Cooperative Bank of Oromia) adapter."""

import sys
from adapters.cbo.adapter import CBOAdapter

def test_cbo():
    print("=== Testing CBO (Cooperative Bank of Oromia) Adapter ===\n")
    
    adapter = CBOAdapter()
    print(f"Adapter key: {adapter.get_adapter_key()}")
    print(f"Source URL: {adapter.get_source_url()}")
    print()
    
    # Fetch raw content
    print("Fetching raw content...")
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://coopbankoromia.com.et/",
        }
        resp = requests.get(adapter.get_source_url(), headers=headers, timeout=15)
        raw_content = resp.text
        http_status = resp.status_code
        print(f"HTTP Status: {http_status}")
        print(f"Content length: {len(raw_content)} bytes")
        print()
    except Exception as e:
        print(f"❌ FETCH FAILED: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Parse content
    print("Parsing content...")
    try:
        result = adapter.parse(raw_content)
        print(f"✓ Parse completed")
        print(f"  Records found: {len(result.records)}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Warnings: {len(result.warnings)}")
        print()
        
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
            print("SAMPLE RECORDS:")
            for i, rec in enumerate(result.records[:5]):
                print(f"  [{i+1}] {rec.source_currency_code} {rec.category}: "
                      f"Buy {rec.buying_rate} / Sell {rec.selling_rate} "
                      f"(effective: {rec.effective_date})")
            if len(result.records) > 5:
                print(f"  ... and {len(result.records) - 5} more")
            print()
            
            # Check for USD transactional
            usd_trans = [r for r in result.records 
                        if r.source_currency_code == 'USD' and r.category == 'transactional']
            if usd_trans:
                print(f"✓ Found {len(usd_trans)} USD transactional record(s)")
                for rec in usd_trans:
                    print(f"  USD transactional: Buy {rec.buying_rate} / Sell {rec.selling_rate}")
            else:
                print("⚠ No USD transactional records found!")
                
                # Show what we do have
                currencies = set(r.source_currency_code for r in result.records)
                categories = set(r.category for r in result.records)
                print(f"  Currencies found: {sorted(currencies)}")
                print(f"  Categories found: {sorted(categories)}")
        else:
            print("❌ NO RECORDS EXTRACTED")
            
    except Exception as e:
        print(f"❌ PARSE FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == "__main__":
    test_cbo()
