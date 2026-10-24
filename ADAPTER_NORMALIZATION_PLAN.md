# Adapter Category Normalization - Implementation Plan

**Date**: October 21, 2026  
**Status**: Ready to Execute  
**Goal**: Apply category normalization to all 32 adapters systematically

---

## Current State

**Audit Results**:
- 🔴 **1 Critical** - Wegagen (has UNKNOWN → data invisible)
- 🟡 **7 High Priority** - Hard-coded categories without normalization
- 🟢 **24 Medium** - Need review and normalization
- ✓ **0** Currently using normalizer

**Problem**: Each adapter handles categories inconsistently → data quality issues

---

## Implementation Strategy

### Phase 1: CRITICAL (Today) - Fix Invisible Data
**Adapters**: Wegagen  
**Issue**: Uses `category="UNKNOWN"` → ALL data filtered from trusted view  
**Impact**: Oct 21 data exists but invisible in UI

### Phase 2: HIGH Priority (This Week) - Hard-Coded Categories
**Adapters**: 7 adapters with explicit category strings  
**Issue**: Hard-coded strings may not match canonical values  
**Impact**: Potential inconsistency, hard to maintain

### Phase 3: MEDIUM Priority (Next Sprint) - Systematic Normalization
**Adapters**: All remaining 24 adapters  
**Issue**: Using inline logic instead of centralized normalization  
**Impact**: Code duplication, harder to add new patterns

---

## Adapter Categories by Priority

### 🔴 CRITICAL - Immediate Fix Required

| Adapter | Current Issue | Action |
|---------|--------------|--------|
| wegagen | `category="UNKNOWN"` | Use normalizer with field name hints |

### 🟡 HIGH - Fix This Week

| Adapter | Hard-Coded Values | Action |
|---------|-------------------|--------|
| addis_fortune | "cash", "transactional" | Wrap in `normalize_category()` |
| adib | "transactional", "weighted_average" | Wrap in `normalize_category()` |
| cbo | "weighted_average" | Wrap in `normalize_category()` |
| dashen | "weighted_average" | Wrap in `normalize_category()` |
| gadaa | "transactional" | Wrap in `normalize_category()` |
| oromia | "transactional" | Wrap in `normalize_category()` |
| tsedey | "transactional" | Use normalizer for "non-cash" → "transactional" |

### 🟢 MEDIUM - Systematic Migration

**24 Adapters**: abay, ahadu, amhara, anbesa, awash, berhan, boa, bunna, cbe, dbe, enat, global_, goh_betoch, hibret, nib, omo, rammis, shabelle, sidama, siinqee, siket, tsehay, zamzam, zemen

**Current Approach**: Inline category logic (e.g., parsing table headers)  
**Target**: Use `normalize_category()` on scraped text  

---

## Implementation Pattern

### Pattern 1: Simple String Replacement

**Before**:
```python
category = "transactional"
```

**After**:
```python
from pipeline.category_normalizer import normalize_category
category = normalize_category("transactional")  # Returns "transactional"
```

**Why**: Future-proof, centralizes validation

---

### Pattern 2: Scraped Text Normalization

**Before**:
```python
# Manual mapping
header_text = soup.find("th").text.strip()
if "CASH" in header_text.upper():
    category = "cash"
elif "TRANS" in header_text.upper():
    category = "transactional"
else:
    category = "UNKNOWN"
```

**After**:
```python
from pipeline.category_normalizer import normalize_category

header_text = soup.find("th").text.strip()
category = normalize_category(header_text)  # Handles all variations
```

**Why**: Handles typos, abbreviations, new variations automatically

---

### Pattern 3: Field Name Hints (API adapters)

**Before** (Wegagen example):
```python
# buying == tra_buying → ambiguous
category = "UNKNOWN"
```

**After**:
```python
from pipeline.category_normalizer import normalize_category_with_context

# Use field name as hint
category = normalize_category_with_context("", {"field_name": "tra_buying"})
# → "transactional"
```

**Why**: Leverages API field structure to infer category

---

### Pattern 4: Conditional Logic to Normalization

**Before** (Tsedey example):
```python
category_raw = row.get("category", "").lower()
if category_raw == "non-cash":
    category = "transactional"
elif category_raw == "cash":
    category = "cash"
else:
    category = None
```

**After**:
```python
from pipeline.category_normalizer import normalize_category

category_raw = row.get("category", "")
category = normalize_category(category_raw)  # Handles "non-cash" → "transactional"
```

**Why**: Simpler, handles edge cases automatically

---

## Execution Plan

### Day 1 (Today): CRITICAL

**Wegagen Adapter**

1. Add import:
   ```python
   from pipeline.category_normalizer import normalize_category_with_context
   ```

2. Replace line 107:
   ```python
   # Before
   category="UNKNOWN",
   
   # After - Option A: Use transactional as default
   category=normalize_category("transactional"),
   
   # OR Option B: Use field name hints
   category=normalize_category_with_context("", {"field_name": "tra_buying"}),
   ```

3. Test:
   ```bash
   PYTHONPATH=. python3 -c "
   from adapters.wegagen.adapter import WegagenAdapter
   from db.manager import DatabaseManager
   DatabaseManager.initialize()
   # Run collection, verify category
   "
   ```

4. Verify Oct 21 data now visible in UI

---

### Day 2-5 (This Week): HIGH Priority

**For each of 7 adapters**:

1. Review current category handling
2. Add normalizer import
3. Replace hard-coded strings with `normalize_category()` calls
4. Run adapter test
5. Verify database records have correct category_id

**Order**:
1. tsedey (has "non-cash" → "transactional" mapping)
2. addis_fortune (multiple hard-coded)
3. adib, cbo, dashen, gadaa, oromia (single hard-coded)

---

### Week 2-3 (Next Sprint): MEDIUM Priority

**Batch process 24 remaining adapters**:

**Group A - API Adapters** (Use field name hints):
- cbe, rammis, addis

**Group B - Multi-Table HTML** (Scrape headers):
- dashen, omo, nib, tsehay

**Group C - Wide-Table HTML** (Parse column headers):
- bunna, cbo, amhara, hibret, boa

**Group D - Single-Table** (Context-dependent):
- dbe, siinqee, global_, goh_betoch

**Group E - Text Extraction** (Parse text):
- sidama, enat, ahadu, berhan

---

## Testing Strategy

### Unit Tests

Create `tests/test_category_normalization_integration.py`:

```python
def test_wegagen_normalizes_categories():
    """Wegagen adapter should normalize tra_buying to transactional."""
    from adapters.wegagen.adapter import WegagenAdapter
    adapter = WegagenAdapter()
    # Test with fixture data
    ...

def test_tsedey_normalizes_non_cash():
    """Tsedey 'non-cash' should normalize to 'transactional'."""
    from adapters.tsedey.adapter import TsedeyAdapter
    adapter = TsedeyAdapter()
    # Test with fixture data
    ...
```

### Integration Tests

```bash
# After each adapter update:
1. Run adapter-specific test
2. Verify category_id in database
3. Check trusted view includes records
```

### Regression Tests

```bash
# Ensure no data loss:
SELECT COUNT(*) WHERE category_id IS NULL;
# Should decrease or stay same, never increase
```

---

## Success Criteria

### Phase 1 (Critical)
✅ Wegagen Oct 21 data visible in UI  
✅ No more UNKNOWN records from Wegagen  
✅ Database has wegagen records with category_id NOT NULL

### Phase 2 (High Priority)
✅ All 7 adapters using normalize_category()  
✅ No hard-coded category strings remain  
✅ Tests passing for all 7 adapters

### Phase 3 (Medium Priority)
✅ All 32 adapters using normalization  
✅ Centralized category handling  
✅ Documentation updated

---

## Rollback Plan

If normalization causes issues:

1. **Check normalizer output**:
   ```python
   from pipeline.category_normalizer import normalize_category
   print(normalize_category("problematic_text"))
   ```

2. **Add pattern if needed**:
   ```python
   # In pipeline/category_normalizer.py
   NORMALIZATION_PATTERNS.insert(0, (r'new_pattern', 'canonical_category'))
   ```

3. **Worst case**: Revert adapter to hard-coded (but keep normalizer for future)

---

## Benefits After Completion

1. **Consistency**: All adapters use same normalization logic
2. **Maintainability**: Add one pattern → all adapters benefit
3. **Visibility**: No more hidden data due to category issues
4. **Scalability**: Easy to add new banks with weird naming
5. **Quality**: Centralized validation of categories

---

## Next Steps

1. ✅ Created `pipeline/category_normalizer.py`
2. ✅ Tested with 24 test cases
3. ✅ Created implementation plan
4. ⏭️ **Execute Phase 1**: Fix Wegagen adapter
5. ⏭️ **Execute Phase 2**: Fix 7 high-priority adapters
6. ⏭️ **Execute Phase 3**: Migrate remaining 24 adapters

---

## Decision Log

**Why normalize already-canonical strings?**
- Future-proof: If canonical value changes, update in one place
- Validation: Catches typos early
- Consistency: All adapters use same pattern
- Cost: Minimal (simple string comparison)

**Why not just fix UNKNOWN cases?**
- System-wide problem requires system-wide solution
- Prevents future issues with new adapters
- Makes codebase more maintainable
- Clean code principle: Don't Repeat Yourself (DRY)

**Order of implementation?**
- Critical first (visible impact)
- Then high (code quality)
- Then medium (completeness)
- Pragmatic: Fix what hurts most, then systematically improve
