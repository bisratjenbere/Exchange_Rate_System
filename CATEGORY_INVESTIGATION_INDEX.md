# Category Investigation - Documentation Index

**Investigation Date**: October 21, 2026  
**Issue**: Wegagen Bank data visibility  
**Status**: ✅ Resolved (Phase 1), ⏸️ Enhancement Proposed (Phase 2)

---

## Quick Navigation

### 🚀 Start Here
- **[FIELD_PATTERN_INVESTIGATION_COMPLETE.md](FIELD_PATTERN_INVESTIGATION_COMPLETE.md)** - Executive summary and status

### 📋 For Product Owners
- **[WEGAGEN_FIELD_PATTERN_SUMMARY.md](WEGAGEN_FIELD_PATTERN_SUMMARY.md)** - Problem analysis and business context
- **[CATEGORY_SYSTEM_ANALYSIS.md](CATEGORY_SYSTEM_ANALYSIS.md)** - Why categories exist and matter

### 🏗️ For Architects
- **[docs/decisions/ADR-015-field-structure-category-detection.md](docs/decisions/ADR-015-field-structure-category-detection.md)** - Formal decision record
- **[CATEGORY_NORMALIZATION_SOLUTION.md](CATEGORY_NORMALIZATION_SOLUTION.md)** - Technical solution overview

### 👨‍💻 For Developers
- **[docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md](docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md)** - Implementation patterns
- **[ADAPTER_NORMALIZATION_PLAN.md](ADAPTER_NORMALIZATION_PLAN.md)** - Rollout plan for 32 adapters

### 📚 Related Documentation
- **[docs/decisions/ADR-006.md](docs/decisions/ADR-006.md)** - Source taxonomy (32 banks)
- **[docs/decisions/ADR-011.md](docs/decisions/ADR-011.md)** - Wegagen default category (superseded)

---

## Document Purpose Summary

### Problem Analysis
| Document | Audience | Purpose | Key Content |
|----------|----------|---------|-------------|
| **FIELD_PATTERN_INVESTIGATION_COMPLETE.md** | Everyone | Overview | Problem, solution, status, next steps |
| **WEGAGEN_FIELD_PATTERN_SUMMARY.md** | Product/Technical | Deep dive | Field patterns, no-data-loss principle, engineering decisions |
| **CATEGORY_SYSTEM_ANALYSIS.md** | Product | Business context | What categories are, why they matter, use cases |

### Technical Solutions
| Document | Audience | Purpose | Key Content |
|----------|----------|---------|-------------|
| **ADR-015** | Architects | Decision | No-data-loss principle, field-structure detection |
| **CATEGORY_NORMALIZATION_SOLUTION.md** | Developers | Implementation | How normalizer works, usage patterns |
| **docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md** | Developers | Patterns | Code examples, 5 patterns, testing |

### Planning
| Document | Audience | Purpose | Key Content |
|----------|----------|---------|-------------|
| **ADAPTER_NORMALIZATION_PLAN.md** | Team leads | Execution | Phase 1/2/3 plan, 32 adapters prioritized |

---

## Timeline of Investigation

### Day 1: Problem Discovery
**User Report**: "Wegagen has today's rate posted, but system shows no rate"

**Investigation Steps**:
1. Checked database → Record exists with `is_current=TRUE`
2. Checked category → `category_id=NULL` (UNKNOWN)
3. Checked trusted view query → Excludes `category_id IS NOT NULL`
4. **Root Cause**: UNKNOWN category excluded by design

### Day 2: Root Cause Analysis
**Why UNKNOWN?**
```json
{
  "buying": 162.1739,
  "tra_buying": 162.1739,    // ← Same value, different field
  "selling": 165.4174,
  "tra_selling": 165.4174
}
```

**Adapter Logic**: "Values identical → ambiguous → mark UNKNOWN"

### Day 3-5: Pattern Discovery
**Key Insight**: Field names encode category (not just values)

**Evidence**:
- CBE: `cashBuying` vs `transactionalBuying` (explicit)
- Wegagen: `buying` vs `tra_buying` (prefix convention)
- 32-bank survey: Universal patterns (`cash*`, `tra*`, `weighted*`)

**Principle Established**: Field **structure** > field **values**

### Day 6-7: Solution Design
**Created**:
1. Category normalizer module
2. No-data-loss principle (ADR-015)
3. Field-structure detection patterns

**Updated**:
1. 7 high-priority adapters
2. Wegagen: `UNKNOWN` → `transactional`

**Result**: Wegagen data now visible ✅

### Day 8: Documentation
**Created 5 comprehensive documents** (this index, summaries, patterns, ADR)

---

## Key Concepts

### 1. Category System
**What**: Banks publish 3 types of rates per currency per day
- **Cash**: Physical currency (tourists) - widest spread
- **Transactional**: Wire transfers (businesses) - narrower spread
- **Weighted Average**: Reference rate (reporting) - not tradeable

**Why**: Different transaction types = different rates and risks

**Impact**: Cannot compare different categories (apples to oranges)

---

### 2. Field-Structure Detection
**Principle**: Field names encode category information

| Field Name | Category | Confidence |
|-----------|----------|-----------|
| `cashBuying` | cash | High (explicit) |
| `tra_buying` | transactional | High (prefix convention) |
| `buying` | depends | Low (ambiguous) |

**Decision**: Use field names as category hints via normalizer

---

### 3. No-Data-Loss Principle
**Rule**: When source publishes structurally distinct fields, emit one record per field pair

**Example**:
```
Fields: buying=162.00, tra_buying=162.00 (identical values)
Decision: Emit 2 records (cash + transactional)
Reason: Field existence signals intent, not value equality
```

**Rationale**:
- Storage cheap, lost data expensive
- Values may diverge tomorrow
- Defensive programming
- Aligns with "keep track of all day rate"

---

### 4. Category Normalizer
**Module**: `pipeline/category_normalizer.py`

**Purpose**: Centralized category normalization with pattern matching

**Usage**:
```python
normalize_category("CASH")                     # → "cash"
normalize_category("Transaction")              # → "transactional"
normalize_category("non-cash")                 # → "transactional"
normalize_category_with_context("", {"field_name": "tra_buying"})  # → "transactional"
```

**Benefits**: Handles all variations, context-aware, extensible

---

## Phase Summary

### ✅ Phase 1: Immediate Fix (COMPLETE)
**Goal**: Make Wegagen data visible

**Actions**:
- Created category normalizer
- Updated 7 adapters
- Wegagen: `UNKNOWN` → `transactional`

**Outcome**: ✅ Wegagen Oct 21 data visible in UI

**Files Changed**:
- `pipeline/category_normalizer.py` (new)
- `adapters/wegagen/adapter.py` (category updated)
- 6 other adapters (normalization added)

---

### ⏸️ Phase 2: Field-Structure Detection (PROPOSED)
**Goal**: Complete data capture, handle value divergence

**Action**: ADR-015 - Emit 2 records per currency for Wegagen

**Change**:
```python
# Before: 1 record (transactional default)
records = [AdapterRecord(category="transactional", ...)]

# After: 2 records (field-structure based)
records = [
    AdapterRecord(category="cash", rate=buying, ...),
    AdapterRecord(category="transactional", rate=tra_buying, ...)
]
```

**Outcome**: 20 records per collection (vs. 10 currently)

**Status**: ⏸️ Awaiting owner approval

---

### ⏸️ Phase 3: System-Wide Migration (PLANNED)
**Goal**: Apply normalizer to all 32 adapters

**Timeline**: Next sprint / Q1 2027

**Remaining**: 24 adapters to migrate

---

## Files Created During Investigation

### Core Documentation
1. **FIELD_PATTERN_INVESTIGATION_COMPLETE.md** - This summary
2. **WEGAGEN_FIELD_PATTERN_SUMMARY.md** - Detailed analysis
3. **CATEGORY_INVESTIGATION_INDEX.md** - This index

### Technical Documentation
4. **docs/decisions/ADR-015-field-structure-category-detection.md** - Decision record
5. **docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md** - Pattern guide

### Code Created
6. **pipeline/category_normalizer.py** - Normalization module (24 tests passing)

### Existing Documentation Referenced
7. **CATEGORY_SYSTEM_ANALYSIS.md** - Category system overview
8. **CATEGORY_NORMALIZATION_SOLUTION.md** - Normalizer documentation
9. **ADAPTER_NORMALIZATION_PLAN.md** - Rollout plan
10. **docs/decisions/ADR-006.md** - Source taxonomy
11. **docs/decisions/ADR-011.md** - Wegagen default (superseded)

---

## Reading Paths by Role

### 🎯 Product Owner / Manager
**Goal**: Understand business impact and decisions

**Reading Path**:
1. **FIELD_PATTERN_INVESTIGATION_COMPLETE.md** (10 min) - Overview
2. **CATEGORY_SYSTEM_ANALYSIS.md** (15 min) - Why categories matter
3. **WEGAGEN_FIELD_PATTERN_SUMMARY.md** § "Key Decisions" (5 min)
4. **ADR-015** § "Owner Decision Required" (5 min)

**Total Time**: ~35 minutes

---

### 🏗️ Architect / Tech Lead
**Goal**: Understand technical decisions and trade-offs

**Reading Path**:
1. **FIELD_PATTERN_INVESTIGATION_COMPLETE.md** (10 min) - Overview
2. **ADR-015** (20 min) - Full decision record
3. **CATEGORY_NORMALIZATION_SOLUTION.md** (10 min) - Solution architecture
4. **WEGAGEN_FIELD_PATTERN_SUMMARY.md** § "Engineering Principle" (5 min)

**Total Time**: ~45 minutes

---

### 👨‍💻 Developer (Implementing New Adapter)
**Goal**: Learn patterns and implement correctly

**Reading Path**:
1. **docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md** (20 min) - Patterns
2. **CATEGORY_NORMALIZATION_SOLUTION.md** § "Usage in Adapters" (10 min)
3. **ADR-015** § "Field Pattern Decision Table" (5 min)
4. Reference: `adapters/wegagen/adapter.py` (code example)

**Total Time**: ~35 minutes

---

### 🐛 Developer (Debugging Category Issues)
**Goal**: Understand why adapter marks records as UNKNOWN

**Reading Path**:
1. **CATEGORY_SYSTEM_ANALYSIS.md** § "The UNKNOWN Category Problem" (5 min)
2. **docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md** § "Decision Tree" (5 min)
3. **WEGAGEN_FIELD_PATTERN_SUMMARY.md** § "Verification and Testing" (10 min)
4. Check: `pipeline/category_normalizer.py` (run tests)

**Total Time**: ~20 minutes

---

## Key SQL Queries

### Check Wegagen Current Data
```sql
SELECT 
    source_currency_code,
    rc.code as category,
    buying_rate,
    selling_rate,
    is_current
FROM rate_observation o
LEFT JOIN rate_category rc ON rc.id = o.category_id
WHERE source_id = 27  -- Wegagen
  AND is_current = TRUE
ORDER BY source_currency_code, rc.code;
```

### Monitor for Value Divergence
```sql
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

### Category Distribution Across All Banks
```sql
SELECT 
    b.name,
    COALESCE(rc.code, 'UNKNOWN') as category,
    COUNT(*) as records
FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id
JOIN bank b ON b.id = rs.bank_id
LEFT JOIN rate_category rc ON rc.id = o.category_id
WHERE o.is_current = TRUE
GROUP BY b.name, rc.code
ORDER BY b.name, rc.code;
```

---

## Decision Points for Owner

### Decision 1: Approve ADR-015?
**Question**: Should Wegagen emit 2 records (cash + transactional) per currency?

**Current**: 1 record (transactional default) - 10 records per collection  
**Proposed**: 2 records (field-structure based) - 20 records per collection

**Trade-off**:
- ✅ Pro: Complete data, handles divergence, principled
- ⚠️ Con: 2x storage, apparent duplication

**Recommendation**: Approve (aligns with "keep track of all day rate")

---

### Decision 2: If Not ADR-015, What Mitigation?
**Option A**: Keep Phase 1, add monitoring for value divergence  
**Option B**: Keep Phase 1, revisit if values diverge  
**Option C**: Contact Wegagen to clarify category intent  

---

### Decision 3: Timeline for Phase 2?
**This week**: Immediate implementation  
**Next sprint**: After more evaluation  
**Q1 2027**: With system-wide migration  
**Never**: Stay with Phase 1  

---

## Success Metrics

### Phase 1 (Current)
✅ **Wegagen data visible**: Yes  
✅ **Oct 21 records accessible**: Yes  
✅ **Category normalizer working**: 24/24 tests pass  
✅ **7 adapters updated**: Yes  
✅ **Documentation complete**: Yes (5 documents)

### Phase 2 (If Approved)
⏸️ **2 categories per currency**: Target 20 records  
⏸️ **Handles value divergence**: Automatic  
⏸️ **No code changes needed**: If values diverge tomorrow  
⏸️ **UI shows both categories**: Filter by cash/transactional  

---

## Contact for Questions

**Technical Questions**: Review ADR-015 and patterns documentation  
**Business Questions**: Review CATEGORY_SYSTEM_ANALYSIS.md  
**Implementation Questions**: Review docs/patterns/FIELD_STRUCTURE_CATEGORY_DETECTION.md  

---

## Conclusion

This investigation successfully:
- ✅ Identified root cause (UNKNOWN category exclusion)
- ✅ Discovered universal field patterns across 32 banks
- ✅ Established no-data-loss principle
- ✅ Implemented category normalizer
- ✅ Made Wegagen data visible
- ✅ Proposed long-term solution (ADR-015)
- ✅ Created comprehensive documentation

**Status**: Phase 1 complete, Phase 2 awaiting owner decision.

**Impact**: User can now see Wegagen exchange rates. System has principled approach for category detection across all banks.
