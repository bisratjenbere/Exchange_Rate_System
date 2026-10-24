# ADR-015: Field-Structure-Based Category Detection and No-Data-Loss Principle

Date: 2026-10-21  
Status: PROPOSED — for owner review  
Supersedes: ADR-011 (Wegagen default category)

---

## Context

While investigating why Wegagen Bank's October 21, 2026 data was invisible in the UI (root cause: `category=UNKNOWN` excluded by trusted view query), we discovered a **fundamental ambiguity** in how API adapters should interpret field structures when explicit category labels are missing.

### The Wegagen Case Study

Wegagen Bank's Strapi v4 API returns field structures like this:

```json
{
  "id": 123,
  "attributes": {
    "date": "2026-10-21",
    "code": "USD",
    "buying": 162.1739,
    "tra_buying": 162.1739,    // ← tra = transactional
    "selling": 165.4174,
    "tra_selling": 165.4174,
    "unit": 1
  }
}
```

**The Ambiguity**: When `buying == tra_buying` (values identical), should we:

| Interpretation | Logic | Records Emitted |
|----------------|-------|-----------------|
| A. Redundant fields | Same rate, two names | 1 (deduplicate) |
| B. Different categories | Cash + transactional that happen to equal | 2 (preserve both) |
| C. Ambiguous | Cannot determine without documentation | 1 (category=UNKNOWN) |

The **original Wegagen adapter** chose Interpretation C (conservative), which marked all data as `UNKNOWN` → excluded from trusted view.

**ADR-011** chose Interpretation A (default to `transactional`), which made data visible but potentially lost information.

This ADR proposes **Interpretation B with field-structure detection** as the principled long-term solution.

---

## Decision

### 1. No-Data-Loss Principle (LOCKED)

When a source publishes multiple rate fields with **structurally distinct names** (e.g., `buying` vs. `tra_buying`, `cashBuying` vs. `transactionalBuying`), we must:

> **Emit one record per distinct field pair, even if values are numerically identical**

**Rationale**:
- **Field existence signals publishing intent** — banks don't add redundant fields without reason
- **Storage is cheap, lost data is expensive** — better to store apparent duplicates than lose distinct rates
- **Values being equal is a coincidence, not proof of redundancy** — rates may diverge tomorrow
- **Defensive programming** — if bank starts publishing different values, we already handle it correctly
- **Industry standard: banks publish 3 categories** — cash, transactional, weighted_average

**Counter-example showing why this matters**:
```
Today:    buying = 162.00, tra_buying = 162.00  (identical)
Tomorrow: buying = 162.50, tra_buying = 162.00  (diverged)

If we only emit 1 record today → tomorrow we need schema change logic
If we emit 2 records today → tomorrow just works
```

---

### 2. Field-Structure-Based Category Detection

For API adapters (Types A, B, C) where field names contain category hints, use **field name as category signal**:

```python
from pipeline.category_normalizer import normalize_category_with_context

# Detect field structure and emit record per category
fields = {
    "buying": attrs.get("buying"),
    "tra_buying": attrs.get("tra_buying"),
    "cash_buying": attrs.get("cash_buying"),
    "selling": attrs.get("selling"),
    "tra_selling": attrs.get("tra_selling"),
    "cash_selling": attrs.get("cash_selling"),
}

records = []

# If buying + selling exist → one category (infer from field or default)
if fields["buying"] is not None or fields["selling"] is not None:
    category = normalize_category_with_context("", {"field_name": "buying"})
    records.append(AdapterRecord(
        category=category,  # "cash" or context-dependent
        buying_rate=fields["buying"],
        selling_rate=fields["selling"],
        ...
    ))

# If tra_buying + tra_selling exist → transactional category
if fields["tra_buying"] is not None or fields["tra_selling"] is not None:
    category = normalize_category_with_context("", {"field_name": "tra_buying"})
    records.append(AdapterRecord(
        category=category,  # "transactional"
        buying_rate=fields["tra_buying"],
        selling_rate=fields["tra_selling"],
        ...
    ))

# If cash_buying + cash_selling exist → cash category
if fields["cash_buying"] is not None or fields["cash_selling"] is not None:
    category = normalize_category_with_context("", {"field_name": "cash_buying"})
    records.append(AdapterRecord(
        category=category,  # "cash"
        buying_rate=fields["cash_buying"],
        selling_rate=fields["cash_selling"],
        ...
    ))
```

---

### 3. Field Pattern Decision Table

| Fields Present | Records Emitted | Category Logic | Example |
|----------------|-----------------|----------------|---------|
| `buying` + `tra_buying` | **2** | Field names → cash + transactional | Wegagen |
| `buying` only | **1** | Default or field hint | Ambiguous API |
| `tra_buying` only | **1** | Field name → transactional | Minimal API |
| `cashBuying` + `transactionalBuying` | **2** | Field names → cash + transactional | CBE |
| `cash_buying` + `tra_buying` | **2** | Field names → cash + transactional | Explicit API |
| `buying` + `selling` (single pair) | **1** | Context-dependent default | Rammis, ADIB |

**Key Insight**: Field **structure** (which fields exist) is more reliable than field **values** (whether they're equal) for determining publishing intent.

---

### 4. Category Normalizer Integration

Use `normalize_category_with_context()` to map field names to canonical categories:

```python
from pipeline.category_normalizer import normalize_category_with_context

# Field name hints
normalize_category_with_context("", {"field_name": "buying"})         # → depends on context
normalize_category_with_context("", {"field_name": "cashBuying"})     # → "cash"
normalize_category_with_context("", {"field_name": "tra_buying"})     # → "transactional"
normalize_category_with_context("", {"field_name": "transactional"})  # → "transactional"
normalize_category_with_context("", {"field_name": "weighted_avg"})   # → "weighted_average"
```

The normalizer handles common patterns:
- `cash*` prefix → "cash"
- `tra*` / `trans*` / `txn*` prefix → "transactional"
- `weighted*` / `avg*` prefix → "weighted_average"

---

## Consequences

### Positive

✅ **Data completeness**: Never lose rates due to field name ambiguity  
✅ **Future-proof**: Handles value divergence without code changes  
✅ **Principled**: "Follow what banks publish" is a clear guideline  
✅ **Automatic**: New fields with category hints work without adapter updates  
✅ **Testable**: Can verify by checking database for expected category counts

### Negative

⚠️ **Apparent duplication**: When `buying == tra_buying`, database has two identical-value records  
⚠️ **Storage overhead**: ~2x records for banks that publish identical rates  
⚠️ **UI consideration**: Need to handle showing "USD: Cash 162.00, Transactional 162.00"

### Neutral

🔹 **Verification required**: Still need to confirm with banks which categories they actually publish  
🔹 **Per-source tuning**: Some adapters may need custom field mapping logic  
🔹 **Deduplication boundary**: Pipeline still deduplicates **exact** duplicates (same category + value)

---

## Implementation

### Phase 1: Update Wegagen Adapter (Immediate)

**Current** (ADR-011 implementation):
```python
# adapters/wegagen/adapter.py line 107
category=normalize_category("transactional"),  # Default, emits 1 record
```

**New** (ADR-015 implementation):
```python
# adapters/wegagen/adapter.py - emit 2 records when both fields exist

def _parse_item(self, item: dict) -> list:
    """Emit records based on field structure, not value equality."""
    # ... existing field extraction ...
    
    records = []
    
    # Cash rate (from buying/selling fields)
    buying = self._safe_rate(attrs.get("buying"))
    selling = self._safe_rate(attrs.get("selling"))
    if buying is not None or selling is not None:
        records.append(AdapterRecord(
            source_currency_code=currency,
            category=normalize_category("cash"),  # buying → cash (Wegagen context)
            buying_rate=buying,
            selling_rate=selling,
            raw_excerpt={"id": item_id, "code": currency, "buying": buying, "selling": selling},
            mapping_notes=["field_structure:buying", "category:cash"],
            ...
        ))
    
    # Transactional rate (from tra_buying/tra_selling fields)
    tra_buying = self._safe_rate(attrs.get("tra_buying"))
    tra_selling = self._safe_rate(attrs.get("tra_selling"))
    if tra_buying is not None or tra_selling is not None:
        records.append(AdapterRecord(
            source_currency_code=currency,
            category=normalize_category("transactional"),
            buying_rate=tra_buying,
            selling_rate=tra_selling,
            raw_excerpt={"id": item_id, "code": currency, "tra_buying": tra_buying, "tra_selling": tra_selling},
            mapping_notes=["field_structure:tra_buying", "category:transactional"],
            ...
        ))
    
    return records
```

**Expected Outcome**: Each Wegagen fetch produces ~20 records (10 currencies × 2 categories) instead of 10.

---

### Phase 2: Update CBE Adapter (This Week)

CBE already emits multiple categories but uses explicit field name matching. Refactor to use field-structure detection:

**Before**:
```python
# Hardcoded field name checks
if "cashBuying" in rate_data:
    category = "cash"
elif "transactionalBuying" in rate_data:
    category = "transactional"
```

**After**:
```python
# Use normalizer with field hints
for field_suffix in ["Buying", "Selling"]:
    for field_prefix in ["cash", "transactional", "weighted"]:
        field_name = f"{field_prefix}{field_suffix}"
        if field_name in rate_data:
            category = normalize_category_with_context("", {"field_name": field_name})
            # Emit record with detected category
```

---

### Phase 3: Apply to Other API Adapters (Next Sprint)

**Type A** (CBE): Already handles multiple categories, refactor to use normalizer  
**Type B1** (Rammis): Single pair → default to transactional (no change needed per ADR-010)  
**Type B2** (Addis): Wide-row API → emit per field pair (similar to Wegagen)  
**Type C1** (Wegagen): Implement as described above

---

## Verification Tests

### Test 1: Wegagen Field Structure

```python
def test_wegagen_emits_two_categories_when_both_fields_present():
    """Wegagen adapter should emit cash + transactional records."""
    adapter = WegagenAdapter()
    
    raw_json = {
        "data": [{
            "id": 1,
            "attributes": {
                "date": "2026-10-21",
                "code": "USD",
                "buying": 162.00,
                "tra_buying": 162.00,  # Same value
                "selling": 165.00,
                "tra_selling": 165.00,
                "unit": 1
            }
        }]
    }
    
    result = adapter.parse(json.dumps(raw_json))
    
    # Should emit 2 records even though values are identical
    assert len(result.records) == 2
    
    categories = {r.category for r in result.records}
    assert categories == {"cash", "transactional"}
    
    # Verify rates are correctly assigned
    cash_record = next(r for r in result.records if r.category == "cash")
    assert cash_record.buying_rate == Decimal("162.00")
    
    txn_record = next(r for r in result.records if r.category == "transactional")
    assert txn_record.buying_rate == Decimal("162.00")
```

### Test 2: Value Divergence Handling

```python
def test_wegagen_handles_divergent_values():
    """When buying != tra_buying, both records should have correct values."""
    raw_json = {
        "data": [{
            "id": 1,
            "attributes": {
                "date": "2026-10-21",
                "code": "USD",
                "buying": 162.50,        # Cash rate
                "tra_buying": 162.00,    # Transactional rate (different!)
                "selling": 165.50,
                "tra_selling": 165.00,
                "unit": 1
            }
        }]
    }
    
    result = adapter.parse(json.dumps(raw_json))
    
    cash_record = next(r for r in result.records if r.category == "cash")
    assert cash_record.buying_rate == Decimal("162.50")
    
    txn_record = next(r for r in result.records if r.category == "transactional")
    assert txn_record.buying_rate == Decimal("162.00")
```

### Test 3: Database Verification

```sql
-- After Wegagen collection, verify 2 categories exist per currency
SELECT 
    source_currency_code,
    rc.code as category,
    buying_rate,
    selling_rate,
    is_current
FROM rate_observation o
JOIN rate_category rc ON rc.id = o.category_id
WHERE source_id = 27  -- Wegagen
  AND effective_date = '2026-10-21'
  AND is_current = TRUE
ORDER BY source_currency_code, rc.code;

-- Expected: 2 rows per currency (cash + transactional)
-- USD | cash          | 162.1739 | 165.4174 | TRUE
-- USD | transactional | 162.1739 | 165.4174 | TRUE
```

---

## Alternatives Considered

### Alternative 1: Deduplicate Identical Values

**Approach**: Emit 2 records, but pipeline deduplicates if values are identical

**Rejected because**:
- Breaks no-data-loss principle
- Requires comparing rates across categories (risky)
- Loses track of what bank actually publishes
- Value equality is temporal (may diverge tomorrow)

---

### Alternative 2: Value-Based Detection

**Approach**: If `buying == tra_buying`, emit 1 record; if different, emit 2

**Rejected because**:
- Makes record count dependent on values (fragile)
- Breaks when values temporarily align
- Requires value comparison logic in adapter
- Violates separation of concerns (adapter shouldn't analyze values)

---

### Alternative 3: Manual Configuration Per Source

**Approach**: Config flag `emit_categories: ["cash", "transactional"]` per source

**Rejected because**:
- Requires manual maintenance
- Doesn't scale to 32+ banks
- Can't auto-detect new field structures
- Field names already encode this information

---

## Related Decisions

- **ADR-011**: Wegagen default category = transactional (superseded by this ADR)
- **ADR-008**: Per-source default_category config (still applies for Type F/G single-pair sources)
- **ADR-006 §4.4**: "When category cannot be determined, emit UNKNOWN" (still applies when NO field hints exist)
- **Category Normalizer**: `pipeline/category_normalizer.py` (used for field name → category mapping)

---

## Open Questions

### Q1: What if `buying` field is cash for one bank but transactional for another?

**Answer**: Use per-adapter context or adapter-specific mapping:

```python
# Wegagen context: buying → cash
category = normalize_category_with_context("", {"field_name": "buying", "adapter": "wegagen"})

# Rammis context: buying → transactional (no tra_buying field exists)
category = normalize_category_with_context("", {"field_name": "buying", "adapter": "rammis"})
```

Or use explicit mapping in adapter:
```python
FIELD_CATEGORY_MAP = {
    "buying": "cash",         # Wegagen: buying = cash
    "tra_buying": "transactional",
}
```

---

### Q2: How to handle 3+ categories (cash, transactional, weighted_average)?

**Answer**: Same principle applies:

```python
fields_to_check = [
    ("cash_buying", "cash_selling", "cash"),
    ("tra_buying", "tra_selling", "transactional"),
    ("weighted_buying", "weighted_selling", "weighted_average"),
    ("avg_buying", "avg_selling", "weighted_average"),
]

for buy_field, sell_field, category_hint in fields_to_check:
    if attrs.get(buy_field) or attrs.get(sell_field):
        records.append(AdapterRecord(
            category=normalize_category(category_hint),
            buying_rate=attrs.get(buy_field),
            selling_rate=attrs.get(sell_field),
            ...
        ))
```

---

### Q3: What about HTML adapters (Type D, E)?

**Answer**: HTML adapters already use table structure or column headers for category detection. This ADR applies primarily to **API adapters (Types A, B, C)** where field names are the primary category signal.

For HTML:
- Type D (multi-table): Table structure → category
- Type E (wide-table): Column headers → category
- Type F (single-table): No signal → default category (ADR-008)

---

## Success Criteria

✅ **Wegagen adapter emits 2 categories** per currency  
✅ **Database has cash + transactional records** for Wegagen  
✅ **UI shows both categories** for Wegagen (if user filters by category)  
✅ **No UNKNOWN records** from Wegagen after implementation  
✅ **Tests pass** for identical and divergent value scenarios  
✅ **Automatic handling** if bank starts publishing different values for cash vs transactional

---

## Timeline

- **Day 1** (Today): Document decision (this ADR)
- **Day 2**: Update Wegagen adapter with field-structure detection
- **Day 3**: Test with Oct 21 data, verify 2 categories in database
- **Week 2**: Refactor CBE adapter to use normalizer
- **Sprint 2**: Apply pattern to Addis API (Type B2)
- **Sprint 3**: Document learnings, update adapter guidelines

---

## Owner Decision Required

This ADR proposes changing the interpretation of Wegagen's field structure from:
- **ADR-011**: Single record with default category (emits 10 records per collection)
- **ADR-015**: Multiple records based on field structure (emits 20 records per collection)

**Benefits**: More complete data, future-proof, principled approach  
**Costs**: Apparent duplication when values are identical, storage overhead

**Recommendation**: Approve ADR-015 as the long-term approach. The no-data-loss principle aligns with "keep track of all day rate" user goal and defensive programming practices.

**Fallback**: If owner prefers minimal duplication, keep ADR-011 but add monitoring for value divergence (alert if `buying != tra_buying` ever occurs).
