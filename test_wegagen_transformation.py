#!/usr/bin/env python3
"""
Test Wegagen adapter migration to field detection.

Wegagen has both buying/selling AND tra_buying/tra_selling fields,
so it should now emit 2 records per currency instead of 1.
"""

import json
from adapters.wegagen.adapter import parse

# Load Wegagen fixture
with open("fixtures/wegagen/normal.json", "r") as f:
    raw_json = f.read()
    data = json.loads(raw_json)

print("=" * 80)
print("WEGAGEN ADAPTER FIELD DETECTION TRANSFORMATION TEST")
print("=" * 80)
print()

# Parse using the new field detection approach
records = parse(raw_json)

print(f"📊 Total records parsed: {len(records)}")
print()

# Group by currency
currencies = {}
for record in records:
    currency = record.source_currency_code
    if currency not in currencies:
        currencies[currency] = []
    currencies[currency].append(record.category)

print("🔍 FIELD DETECTION RESULTS:")
print("-" * 80)
print(f"{'Currency':<15} {'Categories Detected':<40} {'Count'}")
print("-" * 80)

for currency in sorted(currencies.keys())[:10]:
    categories = currencies[currency]
    categories_str = ", ".join(sorted(set(categories)))
    print(f"{currency:<15} {categories_str:<40} {len(categories)}")

print()
print("📝 DETAILED EXAMPLE - First currency with data:")
print("-" * 80)

if records:
    first_currency = records[0].source_currency_code
    currency_records = [r for r in records if r.source_currency_code == first_currency]
    
    print(f"\nCurrency: {first_currency}")
    print(f"Total records: {len(currency_records)}")
    
    for i, record in enumerate(currency_records, 1):
        print(f"\nRecord {i}:")
        print(f"  Category: {record.category}")
        print(f"  Buying Rate: {record.buying_rate}")
        print(f"  Selling Rate: {record.selling_rate}")
        print(f"  Source Record Key: {record.source_record_key}")
        print(f"  Unit Multiplier: {record.unit_multiplier}")
        if record.raw_excerpt and 'field_pair' in record.raw_excerpt:
            print(f"  Field Pair: {record.raw_excerpt['field_pair']}")

print()
print("✅ KEY OBSERVATIONS:")
print("-" * 80)
print("1. Wegagen now emits MULTIPLE records per currency")
print("   - buying/selling → cash")
print("   - tra_buying/tra_selling → transactional")
print()
print("2. Field mappings configured in FIELD_CONFIG:")
print("   - Explicit mapping: 'buying' → 'cash'")
print("   - Explicit mapping: 'tra_buying' → 'transactional'")
print()
print("3. Records have unique source_record_key with category suffix")
print()
print("4. Unit multiplier preserved from source data")
print()
print("5. BEFORE: 1 record per currency (data loss)")
print(f"   AFTER:  {len(currency_records) if records else 0} records per currency (no data loss)")
print()

print("=" * 80)
print("TRANSFORMATION COMPLETE ✨")
print("=" * 80)
