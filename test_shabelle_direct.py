#!/usr/bin/env python3
"""Direct test of Shabelle adapter to see current website data."""

from adapters.shabelle.adapter import ShabelleAdapter
import requests

def test_shabelle():
    print("=== Testing Shabelle Bank Adapter ===\n")
    
    adapter = ShabelleAdapter()
    print(f"Adapter key: {adapter.get_adapter_key()}")
    print(f"Source URL: {adapter.get_source_url()}")
    print()
    
    # Fetch raw content
    print("Fetching raw content...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(adapter.get_source_url(), headers=headers, timeout=15, verify=False)
        raw_content = resp.text
        http_status = resp.status_code
        print(f"HTTP Status: {http_status}")
        print(f"Content length: {len(raw_content)} bytes")
        print()
    except Exception as e:
        print(f"❌ FETCH FAILED: {e}")
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
        
        if result.records:
            # Check effective dates
            dates = set(r.effective_date for r in result.records if r.effective_date)
            print(f"Effective dates found: {sorted(dates)}")
            print()
            
            # Check for USD
            usd_records = [r for r in result.records if r.source_currency_code == 'USD']
            if usd_records:
                print(f"Found {len(usd_records)} USD record(s):")
                for rec in usd_records:
                    print(f"  {rec.effective_date} | {rec.category} | Buy: {rec.buying_rate} Sell: {rec.selling_rate}")
            else:
                print("⚠ No USD records found!")
        else:
            print("❌ NO RECORDS EXTRACTED")
            
    except Exception as e:
        print(f"❌ PARSE FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_shabelle()
