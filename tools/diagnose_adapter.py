#!/usr/bin/env python3
"""
Diagnostic tool to check why bank adapters are failing.

Usage:
    python tools/diagnose_adapter.py boa_html
    python tools/diagnose_adapter.py hibret_html
    python tools/diagnose_adapter.py amhara_html
"""

import sys
import requests
from bs4 import BeautifulSoup
from adapters.banks import boa, hibret, amhara
from adapters.core.contract import ParseContext
from adapters.core.dates import business_date_now


def diagnose(adapter_module, adapter_name):
    """Diagnose why an adapter is failing."""
    print(f"\n{'=' * 80}")
    print(f"DIAGNOSING: {adapter_name}")
    print(f"{'=' * 80}\n")
    
    adapter = adapter_module.ADAPTER
    spec = adapter_module.SPEC
    
    # 1. Check URL accessibility
    print(f"1. Checking URL: {spec.url}")
    try:
        response = requests.get(spec.url, timeout=10)
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Content-Length: {len(response.text)} bytes")
        html = response.text
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # 2. Check for tables
    print(f"\n2. Looking for tables in HTML...")
    soup = BeautifulSoup(html, 'lxml')
    tables = soup.find_all('table')
    print(f"   Found {len(tables)} table(s)")
    
    if not tables:
        print("   ✗ NO TABLES FOUND - Site structure changed!")
        print("   → Check if site now uses JavaScript rendering")
        print("   → Check if URL changed")
        return
    
    # 3. Analyze each table
    print(f"\n3. Analyzing table headers...")
    for idx, table in enumerate(tables):
        print(f"\n   Table #{idx + 1}:")
        
        # Get headers
        first_row = table.find('tr')
        if not first_row:
            print("      ✗ No rows found")
            continue
        
        cells = first_row.find_all(['th', 'td'])
        headers = [cell.get_text(strip=True) for cell in cells]
        print(f"      Headers: {headers}")
        
        # Check if headers match spec
        spec_headers = spec.headers
        matches = {}
        for logical, variants in spec_headers.items():
            matched = False
            for header in headers:
                header_lower = header.lower()
                if any(variant.lower() in header_lower for variant in variants):
                    matches[logical] = header
                    matched = True
                    break
            
            if matched:
                print(f"      ✓ Found '{logical}': {matches[logical]}")
            else:
                print(f"      ✗ Missing '{logical}' - tried: {variants}")
        
        # Check if all required columns found
        missing = set(spec.required) - set(matches.keys())
        if not missing:
            print(f"      ✓ All required columns found!")
        else:
            print(f"      ✗ Missing required: {missing}")
    
    # 4. Try to parse
    print(f"\n4. Attempting to parse...")
    ctx = ParseContext(
        category="cash",
        collection_date=business_date_now(),
        source_id=0
    )
    
    try:
        result = adapter.parse(html, ctx)
        print(f"   Records found: {len(result.records)}")
        print(f"   Issues: {len(result.issues)}")
        
        if result.issues:
            print("\n   Issues detected:")
            for issue in result.issues[:5]:  # Show first 5
                print(f"      • [{issue.severity.value}] {issue.detail}")
        
        if result.records:
            print("\n   Sample records:")
            for record in result.records[:3]:  # Show first 3
                print(f"      • {record.source_currency_code}: {record.buying_rate} / {record.selling_rate}")
        else:
            print("   ✗ NO RECORDS EXTRACTED")
            
    except Exception as e:
        print(f"   ✗ Parse failed: {e}")
        import traceback
        traceback.print_exc()
    
    # 5. Recommendations
    print(f"\n5. Recommendations:")
    if len(tables) == 0:
        print("   → Site may have moved to JavaScript rendering")
        print("   → Check browser DevTools Network tab")
        print("   → Look for AJAX/API endpoints")
    elif len(tables) > 1:
        print("   → Multiple tables found - may need better table selector")
        print("   → Add CSS class or ID to TableSpec")
    else:
        print("   → Update header variants in TableSpec")
        print("   → Check actual header text on website")
    
    print(f"\n{'=' * 80}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python tools/diagnose_adapter.py <adapter_name>")
        print("Examples:")
        print("  python tools/diagnose_adapter.py boa_html")
        print("  python tools/diagnose_adapter.py hibret_html")
        print("  python tools/diagnose_adapter.py amhara_html")
        sys.exit(1)
    
    adapter_name = sys.argv[1]
    
    adapters = {
        "boa_html": (boa, "Bank of Abyssinia"),
        "hibret_html": (hibret, "Hibret Bank"),
        "amhara_html": (amhara, "Amhara Bank"),
    }
    
    if adapter_name not in adapters:
        print(f"Unknown adapter: {adapter_name}")
        print(f"Available: {', '.join(adapters.keys())}")
        sys.exit(1)
    
    module, name = adapters[adapter_name]
    diagnose(module, name)
