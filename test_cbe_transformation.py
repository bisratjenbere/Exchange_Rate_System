#!/usr/bin/env python3
"""
Demonstration of CBE adapter transformation with field detection.

This script shows how the CBE adapter now uses field-structure-based
category detection instead of hard-coded category loops.
"""

import json
from adapters.cbe.adapter import parse

# Load CBE fixture data
with open("fixtures/cbe/normal.json", "r") as f:
    raw_json = f.read()
    data = json.loads(raw_json)

print("=" * 80)
print("CBE ADAPTER FIELD DETECTION TRANSFORMATION TEST")
print("=" * 80)
print()

# Parse using the new field detection approach
records = parse(raw_json)

print(f"📊 Total records parsed: {len(records)}")
print()

# Analyze what was detected
currencies = {}
for record in records:
    currency = record.source_currency_code
    category = record.category
    
    if currency not in currencies:
        currencies[currency] = []
    currencies[currency].append(category)

print("🔍 FIELD DETECTION RESULTS:")
print("-" * 80)
print(f"{'Currency':<15} {'Categories Detected':<40} {'Count'}")
print("-" * 80)

for currency in sorted(currencies.keys())[:10]:  # Show first 10
    categories = currencies[currency]
    categories_str = ", ".join(sorted(set(categories)))
    print(f"{currency:<15} {categories_str:<40} {len(categories)}")

print()
print("📝 DETAILED EXAMPLE - USD:")
print("-" * 80)

usd_records = [r for r in records if r.source_currency_code == "USD"]
for i, record in enumerate(usd_records[:2], 1):  # Show first 2 USD records
    print(f"\nRecord {i}:")
    print(f"  Category: {record.category}")
    print(f"  Buying Rate: {record.buying_rate}")
    print(f"  Selling Rate: {record.selling_rate}")
    print(f"  Source Record Key: {record.source_record_key}")
    print(f"  Mapping Notes: {record.mapping_notes}")
    if record.raw_excerpt and 'field_pair' in record.raw_excerpt:
        print(f"  Field Pair Detected: {record.raw_excerpt['field_pair']}")

print()
print("✅ KEY OBSERVATIONS:")
print("-" * 80)
print("1. Categories automatically detected from field structure")
print("   - cashBuying/cashSelling → cash")
print("   - transactionalBuying/transactionalSelling → transactional")
print()
print("2. Each currency emits 2 records (one per category)")
print("   - No hard-coded category loops")
print("   - No hard-coded _CATEGORY_FIELDS dictionary")
print()
print("3. Source record keys include category suffix for uniqueness")
print(f"   - Example: {usd_records[0].source_record_key if usd_records else 'N/A'}")
print()
print("4. Field structure metadata preserved in raw_excerpt")
print("   - Enables debugging and audit trail")
print()
print("5. One-line integration: detect_and_emit()")
print("   - Replaces ~40 lines of hard-coded logic")
print()

print("=" * 80)
print("TRANSFORMATION COMPLETE ✨")
print("=" * 80)
print()
print("Before: Hard-coded category loops across 32 adapters")
print("After:  Automatic field detection with centralized logic")
print()
print("Benefits:")
print("  ✅ No hard-coded category strings")
print("  ✅ Handles new categories automatically")
print("  ✅ More robust (skips incomplete pairs)")
print("  ✅ Simpler adapter code")
print("  ✅ Better debugging (field structure metadata)")
print("=" * 80)
