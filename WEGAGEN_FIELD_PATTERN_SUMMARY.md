# Wegagen Field Pattern Analysis - Executive Summary

**Date**: October 21, 2026  
**Status**: Complete Analysis, Implementation Pending  
**Related**: ADR-015, CATEGORY_SYSTEM_ANALYSIS.md, CATEGORY_NORMALIZATION_SOLUTION.md

---

## The Problem in Plain English

**User Report**: "Wegagen and Oromia have today's exchange rate posted, but our system shows no rate."

**Root Cause**: Wegagen adapter marks all records as `category=UNKNOWN`, which the trusted view query excludes (by design, per Gap Review Item E).

**Why UNKNOWN?**: Wegagen's API returns both `buying` and `tra_buying` fields **with identical values**:

```json
{
  "buying": 162.1739,
  "tra_buying": 162.1739,
  "selling": 165.4174,
  "tra_selling": 165.4174
}
```

The original adapter developer couldn't determine if these represent:
- A) Same rate published twice (redundant)
- B) Cash + transactional rates that happen to be equal
- C) Ambiguous without bank confirmation

They chose the conservative approach: mark as `UNKNOWN` → exclude from UI.

---

## The Field Pattern Discovery

During investigation, we discovered a **general principle** for how API field names encode category information:

### Field Name → Category Mapping Pattern

| Field Name Pattern | Canonical Category | Examples |
|-------------------|-------------------|----------|
| `cash*` prefix | **cash** | `cashBuying`, `cash_buying`, `Cash` |
| `tra*` / `trans*` prefix | **transactional** | `tra_buying`, `transactionalBuying`, `Transaction` |
| `weighted*` / `avg*` prefix | **weighted_average** | `weighted_buying`, `avg_selling` |
| Plain `buying` (context-dependent) | **depends on bank** | Could be cash OR transactional |

### Real-World Evidence

From survey of 32 Ethiopian banks:

**CBE API** (Type A):
```json
{
  "cashBuying": 161.50,           // ← Field name = cash category
  "cashSelling": 165.00,
  "transactionalBuying": 161.75,  // ← Field name = transactional category
  "transactionalSelling": 164.80
}
```
*Emits 2 records per currency (cash + transactional) with different values.*

**Wegagen API** (Type C1):
```json
{
  "buying": 162.1739,             // ← Ambiguous: cash or transactional?
  "tra_buying": 162.1739,         // ← Clear: transactional
  "selling": 165.4174,
  "tra_selling": 165.4174
}
```
*Both fields exist → bank publishes both categories (even if values currently equal).*

**Rammis API** (Type B1):
```json
{
  "buying": 161.60,               // ← Only one field → default to transactional
  "selling": 164.90
}
```
*Only one pair → use default category (transactional per ADR-010).*

---

## The Key Insight: Field Existence vs. Value Equality

### What We Initially Thought
"If `buying == tra_buying`, they're the same rate → emit 1 record"

### What We Now Understand
"If both `buying` and `tra_buying` **fields exist**, bank intends to publish both categories → emit 2 records, regardless of values"

### Why This Matters

**Scenario**: Banks typically publish 3 categories
- **Cash**: For physical currency exchange (tourists)
- **Transactional**: For wire transfers (businesses)
- **Weighted Average**: Calculated reference rate (reporting)

**Industry Standard**: Most banks publish different rates for cash vs. transactional:
- Cash spread wider (e.g., buy 161.50, sell 165.00 = 3.50 Birr spread)
- Transactional spread narrower (e.g., buy 161.75, sell 164.80 = 3.05 Birr spread)

**Wegagen Edge Case**: Currently publishes **identical** values for both categories:
```
Today: buying = 162.00, tra_buying = 162.00
```

**But this doesn't mean they're redundant!**
- **Field structure** (both exist) signals intent to publish both
- **Value equality** is a coincidence or policy decision
- **Tomorrow they might diverge**: `buying = 162.50, tra_buying = 162.00`

---

## The No-Data-Loss Principle

### Decision Rule (ADR-015)

> **When a source publishes structurally distinct fields (e.g., `buying` vs. `tra_buying`), emit one record per field pair, even if values are numerically identical.**

### Field Pattern Decision Table

| Fields Present | Records Emitted | Logic |
|----------------|-----------------|-------|
| `buying` + `tra_buying` | **2** (cash + transactional) | Both fields exist → both categories intended |
| `only tra_buying` | **1** (transactional) | Only transactional published |
| `only buying` | **1** (default: transactional) | Ambiguous → use default per ADR-010 |
| `cash_buying` + `tra_buying` | **2** (cash + transactional) | Explicit field names → clear intent |
| `cashBuying` + `transactionalBuying` + `weightedBuying` | **3** (all categories) | Full category set |

### Rationale for No-Data-Loss

1. **Field existence signals intent**
   - Banks don't add redundant API fields without reason
   - If they publish `buying` AND `tra_buying`, they mean to distinguish them

2. **Storage is cheap, lost data is expensive**
   - Better to store apparent duplicates than lose distinct rates
   - Disk space: ~200 bytes per record × 20 records = 4 KB per collection
   - Lost business intelligence: priceless

3. **Value equality is temporal**
   - Today: identical values
   - Tomorrow: values diverge
   - If we only emit 1 record today, tomorrow requires schema change logic

4. **Defensive programming**
   - Design for what might happen, not just what we observe today
   - If bank policy changes, system adapts automatically

5. **Aligns with user goal**
   - User: "Keep track of all day rate"
   - If bank publishes 2 rates → we track 2 rates

---

## The Solution: Category Normalizer

### Created Module: `pipeline/category_normalizer.py`

Centralized pattern-based normalization with context awareness:

```python
from pipeline.category_normalizer import normalize_category_with_context

# Field name as category hint
normalize_category_with_context("", {"field_name": "cashBuying"})     # → "cash"
normalize_category_with_context("", {"field_name": "tra_buying"})     # → "transactional"
normalize_category_with_context("", {"field_name": "weighted_avg"})   # → "weighted_average"

# Text-based normalization (for HTML adapters)
normalize_category("CASH")                    # → "cash"
normalize_category("Transaction")             # → "transactional"
normalize_category("non-cash")                # → "transactional"
normalize_category("Weighted Average Rate")   # → "weighted_average"
```

**Benefits**:
- ✅ Handles all variations (CASH, Cash, cash, cash_buying)
- ✅ Context-aware (field names, column headers)
- ✅ Extensible (add pattern → all adapters benefit)
- ✅ Returns UNKNOWN when ambiguous (intentional flag)

---

## Implementation Status

### Phase 1: Immediate Fix (Completed Oct 21)
✅ **Created**: `pipeline/category_normalizer.py`  
✅ **Updated**: 7 high-priority adapters to use normalizer:
- Wegagen: Changed `UNKNOWN` → `normalize_category("transactional")`
- Tsedey, Addis Fortune, ADIB, CBO, Dashen, Gadaa, Oromia: Wrapped hard-coded strings

✅ **Result**: Wegagen Oct 21 data now visible in UI

### Phase 2: Field-Structure Detection (Pending)
⏸️ **ADR-015 Proposed**: Implement field-structure-based detection for Wegagen  
⏸️ **Changes Required**:
- Wegagen adapter: Emit 2 records (cash from `buying`, transactional from `tra_buying`)
- CBE adapter: Refactor to use normalizer (already emits multiple categories)
- Addis adapter: Wide-row handling (similar to Wegagen)

⏸️ **Expected Outcome**:
- Wegagen: 10 records → 20 records per collection (2 categories per currency)
- Database: `SELECT COUNT(*) WHERE source_id=27 AND effective_date='2026-10-21'` shows 20 rows
- UI: Can filter by category (cash vs. transactional)

### Phase 3: System-Wide Migration (Planned)
⏸️ **Apply normalizer to remaining 24 adapters**  
⏸️ **Create documentation**: Adapter development guidelines  
⏸️ **Update tests**: Category detection test suite

---

## How Banks Actually Publish Rates

### Common Patterns (from 32-bank survey)

**Pattern 1: Explicit Field Names (CBE, some others)**
```json
{
  "cashBuying": 161.50,
  "cashSelling": 165.00,
  "transactionalBuying": 161.75,
  "transactionalSelling": 164.80,
  "weightedAverageBuying": 163.00,
  "weightedAverageSelling": 164.50
}
```
*Clear: 3 categories with different values.*

**Pattern 2: Prefix Convention (Wegagen)**
```json
{
  "buying": 162.17,          // Possibly cash?
  "tra_buying": 162.17,      // Definitely transactional
  "selling": 165.42,
  "tra_selling": 165.42
}
```
*Ambiguous: Does `buying` = cash or is it redundant?*

**Pattern 3: Single Pair (Rammis, ADIB, many others)**
```json
{
  "buying": 161.60,
  "selling": 164.90
}
```
*Ambiguous: Could be cash OR transactional. Use default per ADR-010.*

**Pattern 4: Multi-Table HTML (Dashen, Omo, NIB)**
```html
<table id="cash">...</table>
<table id="transactional">...</table>
<table id="weighted_average">...</table>
```
*Clear: Separate tables = separate categories.*

**Pattern 5: Wide-Table HTML (Bunna, CBO, BOA)**
```
| Currency | Cash Buy | Cash Sell | Txn Buy | Txn Sell | Avg Buy | Avg Sell |
```
*Clear: Column headers indicate categories.*

---

## The Engineering Principle

### Hard-Coding vs. Flexible Approach

**Initial Approach** (hard-coding):
```python
# Wegagen adapter
category = "transactional"  # Assumption: tra_buying is primary
```

**Problem**:
- What if bank adds `cash_buying` field tomorrow?
- What if values diverge?
- Requires code change to adapt

**Flexible Approach** (field-structure detection):
```python
# Detect which fields exist
if "buying" in data and "tra_buying" in data:
    # Both exist → emit both categories
    emit_record(category="cash", rate=data["buying"])
    emit_record(category="transactional", rate=data["tra_buying"])
elif "tra_buying" in data:
    # Only transactional
    emit_record(category="transactional", rate=data["tra_buying"])
else:
    # Default
    emit_record(category="transactional", rate=data["buying"])
```

**Benefits**:
- ✅ Adapts to schema changes automatically
- ✅ Handles value divergence without code change
- ✅ Captures complete picture of what bank publishes
- ✅ Senior engineering: design for change, not just current state

---

## Verification and Testing

### How to Verify Implementation

**Step 1: Check Database After Collection**
```sql
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
```

**Expected with ADR-011** (current):
```
USD | transactional | 162.1739 | 165.4174 | TRUE
EUR | transactional | 184.1234 | 187.8012 | TRUE
...
(10 currencies × 1 category = 10 rows)
```

**Expected with ADR-015** (proposed):
```
USD | cash          | 162.1739 | 165.4174 | TRUE
USD | transactional | 162.1739 | 165.4174 | TRUE
EUR | cash          | 184.1234 | 187.8012 | TRUE
EUR | transactional | 184.1234 | 187.8012 | TRUE
...
(10 currencies × 2 categories = 20 rows)
```

**Step 2: UI Verification**
- Navigate to Wegagen bank page
- Should see rates for Oct 21
- If category filter exists, can toggle between cash and transactional

**Step 3: Monitor for Value Divergence**
```sql
-- Alert if buying != tra_buying (field values diverge)
SELECT 
    effective_date,
    source_currency_code,
    raw_data->>'buying' as buying,
    raw_data->>'tra_buying' as tra_buying
FROM rate_observation
WHERE source_id = 27
  AND raw_data->>'buying' IS DISTINCT FROM raw_data->>'tra_buying'
LIMIT 10;
```

---

## Key Decisions and Trade-offs

### Decision 1: Single Record (ADR-011) vs. Multiple Records (ADR-015)

| Approach | Records | Storage | Data Loss Risk | Future-Proof |
|----------|---------|---------|----------------|--------------|
| ADR-011: Single | 10 | Minimal | Medium (if values diverge) | No |
| ADR-015: Multiple | 20 | 2x | None | Yes |

**Current**: ADR-011 (single record with default category)  
**Proposed**: ADR-015 (multiple records based on field structure)  
**Recommendation**: ADR-015 for long-term robustness

---

### Decision 2: When to Use Field-Structure Detection

**Use when**:
- ✅ API adapter with structured field names
- ✅ Multiple field pairs exist (e.g., `buying` + `tra_buying`)
- ✅ Field names contain category hints

**Don't use when**:
- ❌ HTML adapter (use table/column structure instead)
- ❌ Single field pair with no hints (use default category)
- ❌ Field names are generic (`rate1`, `rate2` with no semantic meaning)

---

### Decision 3: Value Equality Should Not Affect Record Count

**Wrong approach**:
```python
if buying == tra_buying:
    emit_one_record()
else:
    emit_two_records()
```
*Problem: Makes logic dependent on data values (fragile)*

**Right approach**:
```python
if "buying" in data:
    emit_record(category=detect_from_field_name("buying"))
if "tra_buying" in data:
    emit_record(category=detect_from_field_name("tra_buying"))
```
*Benefit: Logic based on structure (stable)*

---

## Lessons Learned

### 1. Field Names Are Documentation

When API designers name fields `tra_buying` instead of just `buying2`, they're encoding semantic meaning. Respect that signal.

### 2. Current Values Don't Predict Future Values

Just because `buying == tra_buying` today doesn't mean it will tomorrow. Design for the general case.

### 3. Defensive Programming Over Optimization

Better to store duplicate-looking data than to lose distinct information. Storage is cheap, data reconstruction is expensive.

### 4. Pattern Recognition Across Banks

Looking at 32 banks' field structures revealed universal patterns:
- `cash*` prefix → cash category
- `tra*` / `trans*` prefix → transactional category
- `weighted*` / `avg*` prefix → weighted_average category

These patterns transcend individual banks → general solution.

### 5. Conservative Flagging vs. Aggressive Inference

Original Wegagen adapter: conservative (mark UNKNOWN)  
ADR-011 approach: moderate (default to transactional)  
ADR-015 approach: complete (emit both, let data speak)

Each has trade-offs. ADR-015 balances completeness with minimal guessing.

---

## Next Steps

### Immediate (Today)
✅ **Document findings** (this file)  
✅ **Create ADR-015** for formal decision  
⏸️ **Owner review** of ADR-015 proposal

### Short-term (This Week)
⏸️ **Implement ADR-015** in Wegagen adapter  
⏸️ **Test with Oct 21 data** and verify database  
⏸️ **Refactor CBE adapter** to use category normalizer

### Medium-term (Next Sprint)
⏸️ **Apply to Addis API** (Type B2 wide-row)  
⏸️ **Create adapter development guide** with field-structure patterns  
⏸️ **Update documentation** for onboarding new adapters

### Long-term (Q1 2027)
⏸️ **Migrate all 32 adapters** to use category normalizer  
⏸️ **Monitor for field structure changes** across banks  
⏸️ **Machine learning model** for ambiguous category detection (if needed)

---

## Related Documentation

- **ADR-015**: Field-Structure-Based Category Detection (this decision)
- **ADR-011**: Wegagen default category = transactional (superseded by ADR-015)
- **ADR-010**: Rammis default category = transactional (single-pair API)
- **ADR-008**: Per-source default_category config (Type F/G)
- **ADR-006 §4.4**: Category identification patterns across 32 banks
- **CATEGORY_SYSTEM_ANALYSIS.md**: What categories are and why they matter
- **CATEGORY_NORMALIZATION_SOLUTION.md**: How the normalizer works
- **ADAPTER_NORMALIZATION_PLAN.md**: Phased rollout to all adapters

---

## Questions and Answers

### Q: Why not just ask Wegagen which category they publish?

**A**: We should! But while waiting for confirmation, we need a principled approach. Field-structure detection is defensible because:
- It respects what they publish (both fields exist)
- It adapts if they change (no code changes needed)
- It's testable (can verify in database)

### Q: What if the apparent duplicates confuse users?

**A**: UI can handle this:
- **Option 1**: Show both with note "Cash and transactional rates are currently identical"
- **Option 2**: Default view shows one category, advanced view shows all
- **Option 3**: Highlight when categories differ (value divergence alert)

### Q: Does this apply to HTML adapters too?

**A**: Partially. HTML adapters use:
- **Table structure** (Type D: separate tables per category)
- **Column headers** (Type E: wide table with category spans)
- **Default category** (Type F: single table, no label)

Field-structure detection is primarily for **API adapters** (Types A, B, C) where field names encode category.

### Q: What happens if we're wrong about the categories?

**A**: System handles correction gracefully:
1. **Change adapter code**: Update category mapping
2. **Re-collect data**: New records with correct categories
3. **Old records marked not current**: `is_current=FALSE`
4. **Trusted view shows only new**: Query filters on `is_current=TRUE`

No data loss, just version change.

---

## Conclusion

The Wegagen field pattern analysis revealed a **general principle**: 

> **When sources publish structurally distinct fields, respect that structure and emit multiple records, even if current values are identical.**

This principle:
- ✅ Preserves all information banks publish
- ✅ Adapts to future changes automatically
- ✅ Aligns with defensive programming
- ✅ Scales to other banks with similar patterns
- ✅ Supports the user goal: "keep track of all day rate"

**Recommendation**: Implement ADR-015 (field-structure-based detection) as the long-term solution for API adapters.

**Current Status**: ADR-011 (default category) is working but loses information if values diverge. ADR-015 proposed to address this.
