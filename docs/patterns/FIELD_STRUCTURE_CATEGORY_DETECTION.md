# Field-Structure-Based Category Detection - Pattern Guide

**For**: Adapter developers  
**When**: Working with JSON APIs that publish multiple rate categories  
**Related**: ADR-015, `pipeline/category_normalizer.py`

---

## Quick Reference: Field Names → Categories

### Common Field Name Patterns

| If field name contains... | Category | Examples |
|---------------------------|----------|----------|
| `cash` | **cash** | `cashBuying`, `cash_buying`, `CashRate` |
| `tra` or `trans` or `txn` | **transactional** | `tra_buying`, `transactionalSelling`, `txnRate` |
| `weighted` or `avg` or `average` | **weighted_average** | `weighted_buying`, `avgRate`, `AverageRate` |
| `indicative` or `reference` | **indicative_reference** | `indicativeRate`, `referenceRate` |

### Ambiguous Field Names

| Field name | Likely category | Decision rule |
|------------|----------------|---------------|
| `buying` / `selling` (alone) | **depends** | Check adapter context or use default |
| `rate` / `exchange_rate` | **unknown** | Need more context |
| `spot` / `market` | **unknown** | Verify with bank |

---

## Pattern 1: Multiple Explicit Fields (CBE-style)

### Source Response
```json
{
  "Currency": "USD",
  "cashBuying": 161.50,
  "cashSelling": 165.00,
  "transactionalBuying": 161.75,
  "transactionalSelling": 164.80
}
```

### Detection Logic
```python
from pipeline.category_normalizer import normalize_category_with_context

# Detect cash category
if "cashBuying" in data or "cashSelling" in data:
    records.append(AdapterRecord(
        category=normalize_category_with_context("", {"field_name": "cashBuying"}),  # → "cash"
        buying_rate=data.get("cashBuying"),
        selling_rate=data.get("cashSelling"),
        ...
    ))

# Detect transactional category  
if "transactionalBuying" in data or "transactionalSelling" in data:
    records.append(AdapterRecord(
        category=normalize_category_with_context("", {"field_name": "transactionalBuying"}),  # → "transactional"
        buying_rate=data.get("transactionalBuying"),
        selling_rate=data.get("transactionalSelling"),
        ...
    ))
```

**Result**: 2 records per currency (cash + transactional)

---

## Pattern 2: Prefix Convention (Wegagen-style)

### Source Response
```json
{
  "code": "USD",
  "buying": 162.17,
  "selling": 165.42,
  "tra_buying": 162.17,
  "tra_selling": 165.42
}
```

### Detection Logic
```python
from pipeline.category_normalizer import normalize_category_with_context

records = []

# Cash rate (from buying/selling)
if "buying" in data or "selling" in data:
    records.append(AdapterRecord(
        category=normalize_category("cash"),  # Adapter context: buying = cash
        buying_rate=data.get("buying"),
        selling_rate=data.get("selling"),
        mapping_notes=["field_structure:buying", "category:cash"],
        ...
    ))

# Transactional rate (from tra_buying/tra_selling)
if "tra_buying" in data or "tra_selling" in data:
    records.append(AdapterRecord(
        category=normalize_category_with_context("", {"field_name": "tra_buying"}),  # → "transactional"
        buying_rate=data.get("tra_buying"),
        selling_rate=data.get("tra_selling"),
        mapping_notes=["field_structure:tra_buying", "category:transactional"],
        ...
    ))
```

**Result**: 2 records per currency (cash + transactional)

**Key Point**: Even if `buying == tra_buying`, emit both records (no-data-loss principle)

---

## Pattern 3: Single Pair with Ambiguous Names (Rammis-style)

### Source Response
```json
{
  "currency": "USD",
  "buying": 161.60,
  "selling": 164.90
}
```

### Detection Logic
```python
from pipeline.category_normalizer import normalize_category

# Only one pair → use default category
records.append(AdapterRecord(
    category=normalize_category("transactional"),  # Default per ADR-010
    buying_rate=data.get("buying"),
    selling_rate=data.get("selling"),
    mapping_notes=["single_pair", "default_category:transactional"],
    ...
))
```

**Result**: 1 record per currency (transactional by default)

---

## Pattern 4: Wide Row with All Categories (Addis-style)

### Source Response
```json
{
  "currency": "USD",
  "buying": 161.50,
  "selling": 165.00,
  "transactionBuying": 161.75,
  "transactionSelling": 164.80,
  "weightedBuying": 163.00,
  "weightedSelling": 164.50
}
```

### Detection Logic
```python
from pipeline.category_normalizer import normalize_category_with_context

# Define field groups
field_groups = [
    ("buying", "selling", "cash"),                          # Plain buying → cash
    ("transactionBuying", "transactionSelling", None),      # Auto-detect from name
    ("weightedBuying", "weightedSelling", None),            # Auto-detect from name
]

records = []
for buy_field, sell_field, category_hint in field_groups:
    if buy_field in data or sell_field in data:
        # Use hint if provided, otherwise detect from field name
        if category_hint:
            category = normalize_category(category_hint)
        else:
            category = normalize_category_with_context("", {"field_name": buy_field})
        
        records.append(AdapterRecord(
            category=category,
            buying_rate=data.get(buy_field),
            selling_rate=data.get(sell_field),
            ...
        ))
```

**Result**: Up to 3 records per currency (cash + transactional + weighted_average)

---

## Pattern 5: Dynamic Field Discovery

### Use Case
When you don't know all possible field names in advance.

### Detection Logic
```python
from pipeline.category_normalizer import normalize_category_with_context
import re

# Find all buying/selling pairs dynamically
buying_fields = {k: v for k, v in data.items() if "buying" in k.lower()}
selling_fields = {k: v for k, v in data.items() if "selling" in k.lower()}

# Match pairs by removing "buying"/"selling" suffix
def get_base_name(field_name):
    return re.sub(r'(buying|selling)
</content>
</file>i', '', field_name).rstrip('_')

records = []
processed_bases = set()

for buy_field, buy_value in buying_fields.items():
    base = get_base_name(buy_field)
    if base in processed_bases:
        continue
    
    # Find corresponding selling field
    sell_field = next((k for k in selling_fields if get_base_name(k) == base), None)
    
    # Detect category from field name
    category = normalize_category_with_context("", {"field_name": buy_field})
    
    records.append(AdapterRecord(
        category=category,
        buying_rate=buy_value,
        selling_rate=selling_fields.get(sell_field) if sell_field else None,
        mapping_notes=[f"field_structure:{base}"],
        ...
    ))
    
    processed_bases.add(base)
```

**Result**: Dynamic number of records based on field structure

---

## Implementation Checklist

When implementing field-structure detection in an adapter:

### Step 1: Identify Field Structure
```python
# Print fields for analysis (during development)
print(f"Available fields: {list(data.keys())}")

# Look for patterns:
# - Explicit prefixes (cash*, tra*, weighted*)
# - Paired fields (*Buying + *Selling)
# - Multiple rate pairs vs. single pair
```

### Step 2: Choose Pattern
- [ ] Multiple explicit fields → **Pattern 1**
- [ ] Prefix convention → **Pattern 2**  
- [ ] Single ambiguous pair → **Pattern 3**
- [ ] Wide row all categories → **Pattern 4**
- [ ] Unknown structure → **Pattern 5**

### Step 3: Implement Detection
```python
from pipeline.category_normalizer import normalize_category_with_context

# For each detected field pair:
category = normalize_category_with_context("", {"field_name": field_name})
```

### Step 4: Add Mapping Notes
```python
AdapterRecord(
    ...
    mapping_notes=[
        f"field_structure:{field_name}",
        f"category:{category}",
        "pattern:explicit_fields",  # or prefix_convention, single_pair, etc.
    ]
)
```

### Step 5: Test
```python
# Test data with identical values
test_data_identical = {"buying": 162.00, "tra_buying": 162.00, ...}
assert len(parse(test_data_identical)) == 2  # Should emit 2 records

# Test data with different values
test_data_different = {"buying": 162.50, "tra_buying": 162.00, ...}
records = parse(test_data_different)
assert len(records) == 2
assert records[0].buying_rate != records[1].buying_rate
```

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Value-Based Logic
```python
# WRONG: Don't make decisions based on values
if buying == tra_buying:
    emit_one_record()
else:
    emit_two_records()
```

**Why wrong**: Makes record count dependent on data values (fragile)

**Fix**: Base logic on field structure, not values
```python
# RIGHT: Emit record per field structure
if "buying" in data:
    emit_record(field="buying")
if "tra_buying" in data:
    emit_record(field="tra_buying")
```

---

### ❌ Mistake 2: Hard-Coding Categories
```python
# WRONG: Hard-coded category assumptions
category = "transactional"  # Assumption
```

**Why wrong**: Doesn't scale, requires code change if bank adds categories

**Fix**: Detect from field names
```python
# RIGHT: Detect category from field structure
category = normalize_category_with_context("", {"field_name": field_name})
```

---

### ❌ Mistake 3: Skipping Normalizer
```python
# WRONG: Manual category assignment
if "cash" in field_name.lower():
    category = "cash"
elif "trans" in field_name.lower():
    category = "transactional"
```

**Why wrong**: Duplicates logic, misses edge cases, not centralized

**Fix**: Use category normalizer
```python
# RIGHT: Use centralized normalizer
from pipeline.category_normalizer import normalize_category_with_context
category = normalize_category_with_context("", {"field_name": field_name})
```

---

### ❌ Mistake 4: Assuming Field Order
```python
# WRONG: Assuming first field is cash, second is transactional
fields = list(data.keys())
category = "cash" if i == 0 else "transactional"
```

**Why wrong**: Field order may change, assumption may be wrong

**Fix**: Detect from field names
```python
# RIGHT: Detect from field semantics
for field_name in data.keys():
    if "buying" in field_name.lower():
        category = normalize_category_with_context("", {"field_name": field_name})
```

---

## Testing Strategies

### Test 1: Field Structure Detection
```python
def test_detects_multiple_categories():
    """Adapter should detect categories from field structure."""
    raw_data = {
        "cashBuying": 161.50,
        "cashSelling": 165.00,
        "transactionalBuying": 161.75,
        "transactionalSelling": 164.80,
    }
    
    records = adapter.parse(json.dumps({"data": [raw_data]}))
    
    categories = {r.category for r in records.records}
    assert categories == {"cash", "transactional"}
```

### Test 2: Identical Values
```python
def test_emits_multiple_records_even_when_values_identical():
    """Should emit separate records for each field pair, even if values equal."""
    raw_data = {
        "buying": 162.00,
        "tra_buying": 162.00,  # Same value
        "selling": 165.00,
        "tra_selling": 165.00,
    }
    
    records = adapter.parse(json.dumps({"data": [raw_data]}))
    
    # Should still emit 2 records
    assert len(records.records) == 2
    assert {r.category for r in records.records} == {"cash", "transactional"}
```

### Test 3: Divergent Values
```python
def test_handles_divergent_values_correctly():
    """When values differ, each record should have correct rate."""
    raw_data = {
        "buying": 162.50,        # Cash rate
        "tra_buying": 162.00,    # Transactional rate (lower)
        "selling": 165.50,
        "tra_selling": 165.00,
    }
    
    records = adapter.parse(json.dumps({"data": [raw_data]}))
    
    cash_record = next(r for r in records.records if r.category == "cash")
    txn_record = next(r for r in records.records if r.category == "transactional")
    
    assert cash_record.buying_rate == Decimal("162.50")
    assert txn_record.buying_rate == Decimal("162.00")
```

### Test 4: Missing Fields
```python
def test_handles_missing_fields_gracefully():
    """Should handle when only some fields are present."""
    raw_data = {
        "tra_buying": 162.00,    # Only transactional
        "tra_selling": 165.00,
        # No "buying" or "selling" fields
    }
    
    records = adapter.parse(json.dumps({"data": [raw_data]}))
    
    assert len(records.records) == 1
    assert records.records[0].category == "transactional"
```

---

## Real-World Examples

### Example 1: CBE API (Type A)
**Field Structure**: Explicit category prefixes
```json
{
  "Currency": "USD",
  "cashBuying": 161.50,
  "cashSelling": 165.00,
  "transactionalBuying": 161.75,
  "transactionalSelling": 164.80
}
```

**Implementation**: Pattern 1 (explicit fields)  
**Records Emitted**: 2 (cash + transactional)  
**Category Detection**: Field name directly encodes category

---

### Example 2: Wegagen API (Type C1)
**Field Structure**: Prefix convention
```json
{
  "buying": 162.17,
  "tra_buying": 162.17,
  "selling": 165.42,
  "tra_selling": 165.42
}
```

**Implementation**: Pattern 2 (prefix convention)  
**Records Emitted**: 2 (cash + transactional)  
**Category Detection**: `tra_` prefix → transactional, plain → cash

---

### Example 3: Rammis API (Type B1)
**Field Structure**: Single pair, no hints
```json
{
  "currency": "USD",
  "buying": 161.60,
  "selling": 164.90
}
```

**Implementation**: Pattern 3 (single pair + default)  
**Records Emitted**: 1 (transactional by default)  
**Category Detection**: Default per ADR-010

---

## Decision Tree

```
Does source publish multiple rate pairs?
├─ YES
│  ├─ Do field names have category prefixes?
│  │  ├─ YES (cash*, tra*, weighted*) → Pattern 1 or 2
│  │  └─ NO (rate1, rate2) → Pattern 5 (dynamic) or contact bank
│  └─ Is this a wide-row format?
│     ├─ YES → Pattern 4
│     └─ NO → Pattern 1
│
└─ NO (single pair)
   ├─ Does field name hint category?
   │  ├─ YES (tra_buying) → Use field name hint
   │  └─ NO (buying) → Pattern 3 (default category)
   └─ Is this HTML?
      ├─ YES → Use table/column structure
      └─ NO → Use default per ADR-010
```

---

## Summary

**Key Principle**: Field structure (which fields exist) determines categories, not field values (whether rates are equal).

**Default Rule**: When in doubt, emit multiple records rather than lose information.

**Tool to Use**: `pipeline.category_normalizer.normalize_category_with_context()`

**Testing**: Always test with both identical and divergent values to ensure logic is structure-based, not value-based.

**Documentation**: Add `mapping_notes` to explain field-structure detection logic for future maintainers.
