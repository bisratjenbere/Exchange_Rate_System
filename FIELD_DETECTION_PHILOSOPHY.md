# Field Detection Migration Philosophy

**Date**: October 23, 2026  
**Core Principle**: Dynamic category detection, not hardcoded assumptions

---

## The Problem with Fixed Categorization

❌ **DON'T categorize adapters as:**
- "Single-category adapters" (only transactional)
- "Multi-category adapters" (transactional + cash + weighted_average)

**Why?** Because banks change their published data:
- A "single-category" bank might add cash rates tomorrow
- APIs evolve and add new fields
- Hardcoded assumptions break when reality changes

---

## Universal Approach: Empty Config for All

✅ **ALL adapters should use the same pattern:**

```python
class BankAdapter(FieldStructureMixin, JSONAdapter):
    # Empty config = auto-detect EVERYTHING
    FIELD_CONFIG = {}
```

This means:
1. Field detector finds ALL buying/selling pairs
2. Categories assigned based on field names
3. No assumptions about "how many categories this bank has"
4. System adapts automatically when banks add new data

---

## How It Works

### Step 1: Field Detection Finds Pairs
```python
# Bank data (example)
{
    "buying": "162.00",
    "selling": "165.00",
    "cash_buying": "163.00",
    "cash_selling": "166.00",
    "weighted_buying_average": "164.50",
    "weighted_selling_average": "165.50"
}
```

Field detector automatically discovers:
- `buying` / `selling` → UNKNOWN (generic)
- `cash_buying` / `cash_selling` → cash
- `weighted_buying_average` / `weighted_selling_average` → weighted_average

### Step 2: Category Assignment
- **Explicit prefixes** (cash_, weighted_, trans_) → Detector assigns category
- **Generic fields** (buying, selling) → Assigned UNKNOWN → Needs context

### Step 3: Context-Based Override (if needed)
```python
for rec in detected_records:
    if rec.category == 'UNKNOWN':
        # Use context to determine category
        rec.category = 'transactional'  # or based on array position, field, etc.
```

---

## Real Examples from Our Migrations

### Example 1: ADIB
```python
FIELD_CONFIG = {}  # Empty

# API originally had: transactionBuying, transactionSelling, weightedBuying, weightedSelling
# API changed to: only transactionBuying, transactionSelling
# Empty config handled both - no code changes needed!
```

### Example 2: Gadaa
```python
FIELD_CONFIG = {}  # Empty

# Has: buy_rate, sell_rate, weighted_buy_rate, weighted_sell_rate, market_type field
# Field detector finds both pairs
# market_type field provides explicit category for generic pairs
# System uses hybrid: detection + explicit field
```

### Example 3: Zemen
```python
FIELD_CONFIG = {}  # Empty

# Has: buying_rate, selling_rate, cash_buying_rate, cash_selling_rate
# Two different arrays: day[] and average[]
# Same generic fields mean different categories in different contexts
# Context-based override handles it
```

### Example 4: Oromia (HTML Table)
```python
FIELD_CONFIG = {}  # Empty

# HTML table: Date | Currency | Buying Rate | Selling Rate
# Convert to dict: {"buying_rate": "162.00", "selling_rate": "165.00"}
# Field detector works the same way
# Works for JSON, HTML, any structure converted to dict
```

---

## Migration Steps for ALL Adapters

Same steps for every adapter, regardless of complexity:

### 1. Add Mixin
```python
from field_detection.mixin import FieldStructureMixin

class BankAdapter(FieldStructureMixin, JSONAdapter):
    FIELD_CONFIG = {}
```

### 2. Use detect_and_emit
```python
detected_records = self.detect_and_emit(
    data=row_data,  # dict with field names
    currency=code,
    effective_date=date,
    effective_date_basis=basis
)
```

### 3. Handle UNKNOWN (if needed)
```python
for rec in detected_records:
    if rec.category == 'UNKNOWN':
        # Use context: array name, explicit field, document structure, etc.
        rec.category = determine_from_context(row_data, array_name)
```

### 4. Test
```python
# Test with real API data
# Verify all categories detected
# Check UNKNOWN handling
```

---

## Why This Matters

### Resilience to Change
- **API adds new category**: System detects it automatically
- **API removes category**: No errors, just fewer records
- **Field names change**: Patterns flexible enough to match variations

### No False Assumptions
- Don't assume "bank X only has transactional"
- Don't assume "bank Y always has 3 categories"
- Let the data tell us what categories exist

### Future-Proof
- New category types can be added without touching adapters
- Pattern matching can be enhanced globally
- All adapters benefit from improvements

---

## Pattern Matching Evolution

Field detector patterns have evolved through real-world testing:

### Original Patterns
```python
r"^buying$", r"^selling$"
r"^cashBuying$", r"^cashSelling$"
```

### Added for Real Banks
```python
r"^buy_rate$", r"^sell_rate$"                    # Gadaa
r"^buying_rate$", r"^selling_rate$"              # Zemen
r"^cash_buying_rate$", r"^cash_selling_rate$"    # Zemen
r"^weighted_buying_rate$", r"^weighted_selling_rate$"  # Multiple banks
```

### Still Flexible
- Case-insensitive matching
- Optional underscores: `cash_buying` or `cashbuying`
- Prefix matching: `trans.*buying` matches `transactional_buying`, `transaction_buying`, etc.

---

## Common Patterns We Support

### Pattern 1: Explicit Category Prefixes
```python
# Data
{
    "cashBuying": "163.00",
    "cashSelling": "166.00",
    "transSelling": "165.00",
    "transBuying": "162.00"
}

# Result: auto-detected
# - cash category (2 records)
# - transactional category (2 records)
```

### Pattern 2: Explicit Field with Generic Fields
```python
# Data
{
    "buy_rate": "162.00",
    "sell_rate": "165.00",
    "market_type": "transaction"
}

# Result:
# - buy_rate/sell_rate → UNKNOWN
# - Override using market_type → transactional
```

### Pattern 3: Array Context
```python
# Data
{
    "rates": {
        "day": [{"buying_rate": "162.00", "selling_rate": "165.00"}],
        "average": [{"buying_rate": "164.50", "selling_rate": "165.50"}]
    }
}

# Result:
# - day array → transactional (context-based)
# - average array → weighted_average (context-based)
```

### Pattern 4: Multiple Pairs in One Object
```python
# Data
{
    "buying": "162.00",
    "selling": "165.00",
    "transaction_buying": "162.00",
    "transaction_selling": "165.00",
    "weighted_buying_average": "164.50"
}

# Result:
# - buying/selling → UNKNOWN (filtered as duplicate)
# - transaction_buying/transaction_selling → transactional
# - weighted_buying_average → weighted_average (single field, no pair)
```

---

## Testing Strategy

### For Each Adapter
1. ✅ Run with live API data
2. ✅ Verify record count matches expected
3. ✅ Check all categories discovered
4. ✅ Validate UNKNOWN handling
5. ✅ Ensure no errors

### Don't Trust Documentation
- **Always test with actual API response**
- Documentation gets outdated
- Banks change their APIs
- Field names evolve

---

## Summary

**One approach for all adapters:**
- Empty `FIELD_CONFIG = {}`
- Field detector finds everything
- Context-based override when needed
- No assumptions about categories
- System adapts to changes automatically

**This is not about "single-category" vs "multi-category"**  
**It's about dynamic detection vs hardcoded assumptions**

All adapters should use the same universal pattern. The only differences are:
1. JSON vs HTML (data source format)
2. How to handle UNKNOWN category (context varies)
3. Special fields that provide explicit categories (market_type, array name, etc.)

The migration plan's phases were for estimation only. Implementation should be identical for all.
