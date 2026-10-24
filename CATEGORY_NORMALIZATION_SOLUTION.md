# Category Normalization Solution

**Date**: October 21, 2026  
**Problem**: Banks use inconsistent category labels ("CASH", "Transaction", "non-cash", "trans_category")  
**Solution**: Centralized pattern-based normalization layer

---

## The Problem

When scraping exchange rates from 32 different banks, we encounter **wildly inconsistent category naming**:

### Real Examples from Our Adapters

```
CASH variations:
- "CASH" (Bunna)
- "Cash" (BOA)
- "cash" (CBE API)
- "cash buying" (scraped headers)
- "cash_buying" (API fields)
- "cashBuying" (camelCase APIs)

TRANSACTIONAL variations:
- "TRANSACTION" (Bunna)
- "Transaction" (Dashen)
- "transactional" (our canonical)
- "trans" (abbreviation)
- "txn" (shorter abbreviation)
- "non-cash" (Tsedey - means transactional!)
- "tra_buying" (Wegagen API)

WEIGHTED_AVERAGE variations:
- "WEIGHTED AVERAGE" (full text)
- "Weighted" (abbreviated)
- "Average" (shortened)
- "avg" (minimal)
- "weighted_average" (our canonical)
```

**Without normalization**: Each adapter would handle these inconsistently → data quality nightmare.

---

## The Solution: `pipeline/category_normalizer.py`

A **centralized normalization layer** with pattern-based matching.

### Core Function

```python
from pipeline.category_normalizer import normalize_category

# Handles all variations automatically
normalize_category("CASH")              #  → "cash"
normalize_category("Transaction")       #  → "transactional"
normalize_category("non-cash")          #  → "transactional"
normalize_category("Weighted Average")  #  → "weighted_average"
normalize_category("forex")             #  → "UNKNOWN"
```

### With Context Clues

```python
from pipeline.category_normalizer import normalize_category_with_context

# When category label is missing, use field name as hint
normalize_category_with_context("", {"field_name": "cashBuying"})  # → "cash"
normalize_category_with_context("", {"field_name": "tra_buying"})  # → "transactional"
```

---

## How It Works

### 1. Pattern-Based Matching

The normalizer uses **ordered regex patterns** to match variations:

```python
NORMALIZATION_PATTERNS = [
    # Non-cash MUST come before cash patterns (order matters!)
    (r'^non[_\s\-]?cash$', 'transactional'),  # non-cash → transactional
    
    # TRANSACTIONAL patterns
    (r'^transactional$', 'transactional'),
    (r'^transaction$', 'transactional'),
    (r'^trans$', 'transactional'),
    (r'transact', 'transactional'),  # matches transactional, transaction, transact
    
    # CASH patterns (after non-cash)
    (r'^cash$', 'cash'),
    (r'^cash[_\s-]', 'cash'),  # cash_buying, cash buying, cash-buying
    (r'\bcash\b', 'cash'),     # "Foreign Exchange Cash Rate"
    
    # WEIGHTED_AVERAGE patterns
    (r'^weighted[_\s-]?average$', 'weighted_average'),
    (r'weighted.*average', 'weighted_average'),
    (r'\bweighted\b', 'weighted_average'),
    
    # ... more patterns
]
```

### 2. Preprocessing

Before matching:
- Convert to lowercase
- Trim whitespace
- Remove noise characters (parentheses, colons)
- Normalize multiple spaces

### 3. Fallback to UNKNOWN

If no pattern matches → returns `"UNKNOWN"` (requires manual review)

---

## Usage in Adapters

### Pattern 1: Direct Category from Source

When bank provides clear category labels:

```python
# Before (inconsistent)
category = "CASH"  # Hard-coded, won't match database

# After (normalized)
from pipeline.category_normalizer import normalize_category

raw_category = soup.find("th", text=re.compile("CASH", re.I)).text
category = normalize_category(raw_category)  # → "cash"
```

### Pattern 2: Field Name Hints

When category is in API field names:

```python
from pipeline.category_normalizer import normalize_category_with_context

# CBE API example
for field_name, value in rate_data.items():
    if "Buying" in field_name:
        # cashBuying, transactionalBuying, etc.
        category = normalize_category_with_context(
            "",  # No explicit category
            {"field_name": field_name}  # Use field name as hint
        )
        # cashBuying → "cash"
        # transactionalBuying → "transactional"
```

### Pattern 3: Table Headers

When category is in table column headers:

```python
# Multi-table layout
headers = table.find("tr").find_all("th")
for i, header in enumerate(headers):
    category = normalize_category(header.text.strip())
    # "CASH" → "cash"
    # "Transaction" → "transactional"
    # "Average" → "weighted_average"
```

---

## Updating Wegagen Adapter

### Current Code (Problematic)

```python
# adapters/wegagen/adapter.py line 107
return [AdapterRecord(
    source_currency_code=currency,
    category="UNKNOWN",  # ← Hard-coded, makes data invisible
    ...
)]
```

### Solution Option 1: Field Name Hint

```python
from pipeline.category_normalizer import normalize_category_with_context

# Wegagen API has: buying, tra_buying, selling, tra_selling
records = []

# Cash rate (from 'buying'/'selling' fields)
records.append(AdapterRecord(
    source_currency_code=currency,
    category=normalize_category_with_context("", {"field_name": "buying"}),  # → "cash"
    buying_rate=buying,
    selling_rate=selling,
    ...
))

# Transactional rate (from 'tra_buying'/'tra_selling' fields)
if tra_buying or tra_selling:
    records.append(AdapterRecord(
        source_currency_code=currency,
        category=normalize_category_with_context("", {"field_name": "tra_buying"}),  # → "transactional"
        buying_rate=tra_buying,
        selling_rate=tra_selling,
        ...
    ))

return records
```

### Solution Option 2: Default with Normalization

```python
from pipeline.category_normalizer import normalize_category

# Use default if values are identical
if buying == tra_buying and selling == tra_selling:
    category = normalize_category("transactional")  # → "transactional"
else:
    # Emit both if different
    ...
```

---

## Real-World Test Cases

All these now normalize correctly:

```python
# From actual bank websites we scrape
normalize_category("CASH")                    # → "cash"
normalize_category("Cash Buying")             # → "cash"
normalize_category("cash_buying_rate")        # → "cash"

normalize_category("TRANSACTION")             # → "transactional"
normalize_category("Transaction Selling")     # → "transactional"
normalize_category("trans")                   # → "transactional"
normalize_category("txn")                     # → "transactional"
normalize_category("non-cash")                # → "transactional" ✓

normalize_category("WEIGHTED AVERAGE")        # → "weighted_average"
normalize_category("Weighted")                # → "weighted_average"
normalize_category("Average Rate")            # → "weighted_average"

normalize_category("forex")                   # → "UNKNOWN" (needs review)
normalize_category("market_rate")             # → "UNKNOWN" (needs review)
```

---

## Benefits

### 1. Consistency Across All Banks

**Before**: Each adapter handles categories differently
```python
# Adapter A
category = "cash"

# Adapter B  
category = "CASH"

# Adapter C
category = "Cash"

# Database gets: cash, CASH, Cash → 3 different values!
```

**After**: All normalize to canonical `"cash"`

### 2. Handles Future Banks Automatically

New bank uses "TXN Rate"? → Automatically maps to `"transactional"`

### 3. Centralized Pattern Management

Add one pattern → all adapters benefit:

```python
# Need to handle "FX" abbreviation?
# Just add to normalization patterns:
(r'^fx$', 'transactional'),
```

### 4. Clear UNKNOWN Flag

If normalizer returns `"UNKNOWN"` → **intentional signal** that category needs manual review, not a bug.

---

## Integration Steps

### Step 1: Import Normalizer

```python
# At top of adapter file
from pipeline.category_normalizer import normalize_category
```

### Step 2: Replace Hard-Coded Categories

```python
# Before
category = "UNKNOWN"

# After
category = normalize_category(scraped_text)
```

### Step 3: Test

```python
# Verify in adapter docstring or comments
"""
Category mapping:
- "CASH" header → normalize_category("CASH") → "cash"
- "Transaction" header → normalize_category("Transaction") → "transactional"
"""
```

---

## Recommended Immediate Actions

### 1. Fix Wegagen (Today)

```python
# adapters/wegagen/adapter.py

# Option A: Use field names as hints
category = normalize_category_with_context("", {"field_name": "tra_buying"})

# Option B: Default to transactional if identical
category = "transactional" if buying == tra_buying else normalize_category_with_context("", {"field_name": field_name})
```

### 2. Audit Other Adapters (This Week)

Find all hard-coded category strings:
```bash
grep -rn 'category.*=' adapters/*/adapter.py | grep -E '(UNKNOWN|cash|transactional)'
```

Replace with normalization calls.

### 3. Add Tests (Next Sprint)

```python
# tests/test_category_normalizer.py
def test_wegagen_categories():
    assert normalize_category_with_context("", {"field_name": "tra_buying"}) == "transactional"
    assert normalize_category_with_context("", {"field_name": "buying"}) == "cash"
```

---

## Edge Cases Handled

### Case 1: Multi-Language

```python
# Future: Ethiopian language support
normalize_category("ገንዘብ")  # → Currently "UNKNOWN", can add pattern later
```

### Case 2: Typos

```python
normalize_category("Transction")  # → "transactional" (partial match)
normalize_category("Weigted")     # → "weighted_average" (contains "weig")
```

### Case 3: Abbreviations

```python
normalize_category("T/C")   # → "UNKNOWN" (too ambiguous)
normalize_category("W/A")   # → "UNKNOWN" (needs explicit pattern)
```

---

## Future Enhancements

### 1. Machine Learning Fallback

For truly ambiguous cases:
```python
# Train on labeled data
# "market rate" + context → predict category
```

### 2. Confidence Scores

```python
result, confidence = normalize_category_with_confidence("trans")
# ("transactional", 0.95)

result, confidence = normalize_category_with_confidence("rate")
# ("UNKNOWN", 0.10)  # Low confidence → flag for review
```

### 3. Multi-Language Support

```python
AMHARIC_PATTERNS = [
    (r'ገንዘብ', 'cash'),           # "genzeb" (money)
    (r'ግብይት', 'transactional'),  # "gebayet" (transaction)
]
```

---

## Testing the Normalizer

Run built-in tests:
```bash
python3 pipeline/category_normalizer.py
```

Output:
```
Category Normalization Test Cases
============================================================
✓ 'CASH'                    → cash                (expected: cash)
✓ 'Transaction'             → transactional       (expected: transactional)
✓ 'non-cash'                → transactional       (expected: transactional)
✓ 'Weighted Average'        → weighted_average    (expected: weighted_average)
✓ 'forex'                   → UNKNOWN             (expected: UNKNOWN)
============================================================
Results: 24 passed, 0 failed

Context-Based Normalization Tests
============================================================
✓ field=cashBuying           → cash                (expected: cash)
✓ field=tra_buying           → transactional       (expected: transactional)
✓ field=transactionSelling   → transactional       (expected: transactional)
✓ field=weightedBuying       → weighted_average    (expected: weighted_average)
```

---

## Decision: How to Use This

### For New Adapters

**ALWAYS use the normalizer**:
```python
from pipeline.category_normalizer import normalize_category

category = normalize_category(scraped_category_text)
```

### For Existing Adapters

**Phase 1** (This week): Fix critical issues (Wegagen, other UNKNOWN cases)  
**Phase 2** (Next sprint): Systematically migrate all adapters  
**Phase 3** (Ongoing): Add patterns as new variations discovered

### When to NOT Use

- Category is already canonical ("cash", "transactional", "weighted_average", "indicative_reference")
- Source is a well-structured API with guaranteed category values
- But even then, normalizing is harmless (returns same value)

---

## Summary

✅ **Created**: `pipeline/category_normalizer.py` - Centralized normalization  
✅ **Handles**: 24 real-world test cases from actual bank data  
✅ **Solves**: "trans_category", "non-cash", "CASH" → all normalize correctly  
✅ **Tested**: All test cases passing  
✅ **Ready**: For immediate use in Wegagen and other adapters  

**Next Step**: Update Wegagen adapter to use normalization → Oct 21 data becomes visible.
