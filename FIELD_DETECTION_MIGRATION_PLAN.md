# Field Detection Migration Plan
**Complete Migration Guide for All Adapters**

## Executive Summary

**Goal**: Migrate all 28 adapters to use the field detection system (`FieldStructureMixin` + `detect_and_emit()`)

**Current Status**:
- ✅ **Migrated**: 4 adapters (CBE, RamMIS, Wegagen, Addis Fortune)
- ⏳ **To Migrate**: 28 adapters
- **Total**: 32 adapters

**Benefits**:
- Consistent category detection across all adapters
- Self-documenting field structures via `FIELD_CONFIG`
- Automatic handling of cash/transactional/weighted_average patterns
- Reduced code duplication
- Easier maintenance

---

## Migration Strategy

### Phase 1: API Adapters (Priority: HIGH)
**Why first**: Simple JSON structure, clear field names, easiest to migrate

1. **ADIB** (`adib_api`) - API adapter
2. **Gadaa** (`gadaa_api`) - API adapter  
3. **Awash** (`awash_ajax`) - AJAX endpoint
4. **Zemen** (`zemen_ajax`) - AJAX endpoint

**Estimated Effort**: 2-4 hours (30-60 min each)

---

### Phase 2: Single-Category HTML Adapters (Priority: MEDIUM)
**Why second**: Only emit one category, simpler migration

5. **Oromia** (`oromia_html`) - transactional only
6. **Dashen** (`dashen_html`) - transactional only
7. **Shabelle** (`shabelle_html`) - needs investigation
8. **Berhan** (`berhan_html`) - needs investigation
9. **Omo** (`omo_html`) - needs investigation
10. **Siinqee** (`siinqee_html`) - needs investigation
11. **Siket** (`siket_html`) - needs investigation
12. **Tsedey** (`tsedey_html`) - already uses normalize_category
13. **Zamzam** (`zamzam_html`) - needs investigation
14. **Sidama** (`sidama_html`) - needs investigation

**Estimated Effort**: 5-10 hours (30-60 min each)

---

### Phase 3: Multi-Category HTML Adapters (Priority: MEDIUM)
**Why third**: More complex - multiple categories per page

15. **BOA** (`boa_html`) - cash + transactional (FIXED recently)
16. **CBO** (`cbo_html`) - cash + transactional + weighted_average
17. **Goh Betoch** (`goh_betoch_html`) - transactional + weighted_average
18. **Tsehay** (`tsehay_html`) - multiple categories
19. **NIB** (`nib_html`) - needs investigation
20. **Hibret** (`hibret_html`) - needs investigation
21. **Bunna** (`bunna_html`) - needs investigation
22. **Amhara** (`amhara_html`) - needs investigation
23. **Abay** (`abay_html`) - needs investigation
24. **DBE** (`dbe_html`) - needs investigation
25. **Global** (`global_html`) - needs investigation
26. **Enat** (`enat_html`) - needs investigation

**Estimated Effort**: 8-15 hours (40-90 min each)

---

### Phase 4: Special Cases (Priority: LOW)
**Why last**: Complex fetching, special handling

27. **Ahadu** (`ahadu_html`) - needs investigation
28. **Anbesa** (`anbesa_browser`) - Playwright browser automation

**Estimated Effort**: 2-4 hours

---

## Migration Checklist (Per Adapter)

### Step 1: Analyze Current Implementation (10 min)
- [ ] Read current adapter code
- [ ] Identify data source format (JSON/HTML)
- [ ] Document field names used (e.g., `cashBuying`, `transSelling`)
- [ ] List categories emitted (cash, transactional, weighted_average)
- [ ] Note any special logic or transformations

### Step 2: Determine Field Pattern (5 min)
Choose the appropriate pattern from `field_detection/detector.py`:

**Pattern A**: Prefix-based (e.g., `cashBuying`, `cashSelling`, `transBuying`, `transSelling`)
```python
FIELD_CONFIG = {
    "pattern": "prefix",
    "prefixes": {
        "cash": "cash",
        "transactional": "trans"
    },
    "buying_suffix": "Buying",
    "selling_suffix": "Selling"
}
```

**Pattern B**: Nested objects (e.g., `cash: {buying, selling}`, `transactional: {buying, selling}`)
```python
FIELD_CONFIG = {
    "pattern": "nested",
    "category_key": "type",  # or direct keys: "cash", "transactional"
    "buying_key": "buying",
    "selling_key": "selling"
}
```

**Pattern C**: Column-based (table columns represent categories)
```python
FIELD_CONFIG = {
    "pattern": "columnar",
    "columns": {
        1: {"type": "cash", "field": "buying"},
        2: {"type": "cash", "field": "selling"},
        3: {"type": "transactional", "field": "buying"},
        4: {"type": "transactional", "field": "selling"}
    }
}
```

**Pattern D**: Self-describing field names (field names already clear, no prefixes needed)
```python
FIELD_CONFIG = {}  # Empty - field names are self-documenting
```

### Step 3: Add Mixin & Configure (10 min)
1. Import mixin:
   ```python
   from field_detection.mixin import FieldStructureMixin
   ```

2. Update class definition:
   ```python
   class MyBankAdapter(FieldStructureMixin, HTMLTableAdapter):
       """..."""
       
       FIELD_CONFIG = {
           # Add appropriate pattern from Step 2
       }
   ```

3. Ensure imports:
   ```python
   from pipeline.category_normalizer import normalize_category  # If not already present
   ```

### Step 4: Replace Category Logic (15-30 min)
Replace manual category assignment with `detect_and_emit()`:

**Before** (manual):
```python
result.records.append(AdapterRecord(
    source_currency_code=currency,
    category="transactional",  # or normalize_category("transactional")
    buying_rate=buying,
    selling_rate=selling,
    # ... other fields
))
```

**After** (field detection):
```python
detected_records = self.detect_and_emit(
    data=row,  # The data dict/object
    currency=currency,
    source_record_id=f"{date}:{currency}",
    effective_date=effective_date,
    currency_name=currency_full_name,  # optional
    mapping_notes=["any", "notes"]  # optional
)
result.records.extend(detected_records)
```

### Step 5: Test Adapter (10 min)
1. Create test script (copy from `test_cbo_direct.py` template)
2. Run adapter and verify:
   - Correct number of records
   - Correct categories assigned
   - All currencies processed
   - No errors/warnings

### Step 6: Verify in Production (5 min)
1. Run scheduler: `PYTHONPATH=. python3 scheduler/run_job.py <adapter_key>`
2. Check database for new observations
3. Verify USD matrix shows correct data

**Total Time Per Adapter**: 55-70 minutes

---

## Detailed Migration Examples

### Example 1: API Adapter (Pattern A - Prefix-based)

**Adapter**: ADIB (`adib_api`)

**Before**:
```python
class ADIBAdapter(BankAdapter):
    def parse(self, raw_json: str) -> ParseResult:
        # ... parse JSON ...
        for item in data:
            # Cash
            result.records.append(AdapterRecord(
                category=normalize_category("cash"),
                buying_rate=item["cashBuying"],
                selling_rate=item["cashSelling"],
                # ...
            ))
            # Transactional
            result.records.append(AdapterRecord(
                category=normalize_category("transactional"),
                buying_rate=item["transBuying"],
                selling_rate=item["transSelling"],
                # ...
            ))
```

**After**:
```python
from field_detection.mixin import FieldStructureMixin

class ADIBAdapter(FieldStructureMixin, BankAdapter):
    
    FIELD_CONFIG = {
        "pattern": "prefix",
        "prefixes": {
            "cash": "cash",
            "transactional": "trans"
        },
        "buying_suffix": "Buying",
        "selling_suffix": "Selling"
    }
    
    def parse(self, raw_json: str) -> ParseResult:
        # ... parse JSON ...
        for item in data:
            detected_records = self.detect_and_emit(
                data=item,
                currency=item["currency"],
                source_record_id=f"{item['date']}:{item['currency']}",
                effective_date=item["date"]
            )
            result.records.extend(detected_records)
```

---

### Example 2: HTML Table (Pattern C - Columnar)

**Adapter**: CBO (`cbo_html`)

**Current**: Manual column index mapping
**Target**: Use field detection with columnar pattern

```python
FIELD_CONFIG = {
    "pattern": "columnar",
    "columns": {
        1: {"type": "cash", "field": "buying"},
        2: {"type": "cash", "field": "selling"},
        3: {"type": "transactional", "field": "buying"},
        4: {"type": "transactional", "field": "selling"}
    }
}
```

---

### Example 3: Single Category (Pattern D - Empty Config)

**Adapter**: Oromia (`oromia_html`)

**Current**: Hardcoded `category="transactional"`
**Target**: Use field detection (even for single category for consistency)

```python
FIELD_CONFIG = {}  # Empty - only transactional category exists

# In parse():
detected_records = self.detect_and_emit(
    data={"buying": buying_rate, "selling": selling_rate},
    currency=currency_code,
    source_record_id=record_key,
    effective_date=eff_date
)
```

---

## Testing Template

Create a test file for each adapter (e.g., `test_<bank>_direct.py`):

```python
#!/usr/bin/env python3
"""Direct test of <Bank> adapter."""

import sys
from adapters.<bank>.adapter import <Bank>Adapter

def test_adapter():
    print("=== Testing <Bank> Adapter ===\n")
    
    adapter = <Bank>Adapter()
    print(f"Adapter key: {adapter.get_adapter_key()}")
    print(f"Source URL: {adapter.get_source_url()}")
    
    # Fetch
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    resp = requests.get(adapter.get_source_url(), headers=headers, timeout=15)
    print(f"HTTP Status: {resp.status_code}\n")
    
    # Parse
    result = adapter.parse(resp.text)
    print(f"✓ Records: {len(result.records)}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Warnings: {len(result.warnings)}\n")
    
    # Show samples
    if result.records:
        for i, rec in enumerate(result.records[:5]):
            print(f"  [{i+1}] {rec.source_currency_code} {rec.category}: "
                  f"Buy {rec.buying_rate} / Sell {rec.selling_rate}")
    
    # Check USD transactional
    usd_trans = [r for r in result.records 
                if r.source_currency_code == 'USD' and r.category == 'transactional']
    if usd_trans:
        print(f"\n✓ Found {len(usd_trans)} USD transactional record(s)")
    else:
        print("\n⚠ No USD transactional found")
        currencies = set(r.source_currency_code for r in result.records)
        categories = set(r.category for r in result.records)
        print(f"  Currencies: {sorted(currencies)}")
        print(f"  Categories: {sorted(categories)}")

if __name__ == "__main__":
    test_adapter()
```

---

## Prioritization Criteria

### High Priority (Do First)
- Adapters currently broken or having issues
- API adapters (simplest structure)
- Most-used currencies/banks

### Medium Priority
- Working adapters with single category
- Working adapters with multiple categories

### Low Priority
- Complex browser-based adapters
- Rarely-used banks

---

## Success Metrics

For each migrated adapter, verify:

- [ ] No parse errors in logs
- [ ] Same number of records as before migration
- [ ] Correct categories assigned (check database)
- [ ] USD transactional appears in matrix view
- [ ] Test script passes
- [ ] Production collection succeeds

---

## Rollback Plan

If migration causes issues:

1. **Immediate**: Revert adapter file from git
2. **Investigate**: Run test script to see error
3. **Fix**: Adjust `FIELD_CONFIG` or `detect_and_emit()` call
4. **Retry**: Test again before committing

---

## Migration Tracking

Create a tracking document to mark progress:

```markdown
## Phase 1: API Adapters
- [ ] ADIB (adib_api)
- [ ] Gadaa (gadaa_api)
- [ ] Awash (awash_ajax)
- [ ] Zemen (zemen_ajax)

## Phase 2: Single-Category HTML
- [ ] Oromia (oromia_html)
- [ ] Dashen (dashen_html)
- [ ] Shabelle (shabelle_html)
... (continue for all)
```

---

## Questions & Decisions

### Q: Should we migrate working adapters that already use `normalize_category()`?
**A**: YES - for consistency and maintainability. Field detection provides self-documentation via `FIELD_CONFIG`.

### Q: What if an adapter has unique field patterns not covered by existing patterns?
**A**: Extend `field_detection/detector.py` with new pattern type, or use Pattern D (empty config) with custom logic.

### Q: Should we migrate browser-based adapters (Anbesa)?
**A**: YES, eventually - but prioritize simpler adapters first.

---

## Timeline Estimate

**Total Effort**: 17-33 hours
- Phase 1 (API): 2-4 hours
- Phase 2 (Single-category): 5-10 hours
- Phase 3 (Multi-category): 8-15 hours
- Phase 4 (Special): 2-4 hours

**Recommended Pace**: 3-5 adapters per day
**Total Duration**: 5-10 working days

---

## Next Steps

1. ✅ Review this plan
2. ⏳ Start with Phase 1 (API adapters) - easiest wins
3. ⏳ Create test scripts for each adapter
4. ⏳ Migrate in phases, testing after each adapter
5. ⏳ Update tracking document as you go
6. ⏳ Document any new patterns discovered

---

## Resources

- **Field Detection Spec**: `.kiro/specs/field-structure-category-detection/`
- **Mixin Code**: `field_detection/mixin.py`
- **Detector Logic**: `field_detection/detector.py`
- **Example (migrated)**: `adapters/cbe/adapter.py`, `adapters/wegagen/adapter.py`
- **Example (needs migration)**: `adapters/boa/adapter.py` (recently fixed but not using field detection yet)

---

**Document Version**: 1.0  
**Created**: 2026-10-22  
**Status**: Ready for execution
