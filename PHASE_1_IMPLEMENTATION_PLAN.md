# 🚀 Phase 1 Implementation Plan: Schema Change Resilience

**Goal**: Reduce schema_change failures by 30-50% through multi-strategy parsing and fuzzy selectors  
**Timeline**: Week 1 (Starting Oct 23, 2026)  
**Priority**: HIGH IMPACT - Addresses #1 failure cause

---

## IMPLEMENTATION STRATEGY

### Task 1.1: Multi-Strategy Parsing ✅ STARTING NOW
**File**: `adapters/base.py` (HTMLTableAdapter)  
**Changes**:
- Add `_find_tables_fuzzy()` method with multiple strategies
- Strategy 1: Exact table selection (current)
- Strategy 2: Fuzzy CSS class matching (regex patterns)
- Strategy 3: Any table element fallback
- Strategy 4: Div-based structure detection (for table → div migrations)

**Impact**: 30% reduction in structural change failures

---

### Task 1.2: Fuzzy Selectors
**File**: `adapters/base.py` (HTMLTableAdapter)  
**Changes**:
- Replace `soup.find_all("table")` with fuzzy selector
- Try multiple patterns: `class="rate.*table"`, `class="exchange.*"`, any table
- Log which strategy succeeded for monitoring

**Impact**: 20% reduction in CSS class rename failures

---

### Task 1.3: Enhanced Field Detection Patterns
**File**: `field_detection/detector.py`  
**Changes**:
- Add regex patterns for numbered variants (buying_1, buying_2)
- Add patterns for hyphenated fields (cash-buying, trans-selling)
- Add patterns for camelCase variations (buyingRate, sellingRate)
- Add patterns for abbreviated forms (buy_r, sell_r, buy_rt)

**Impact**: 15% reduction in field name variation failures

---

### Task 1.4: Div-Based Fallback Parser
**New File**: `adapters/parsers/div_parser.py`  
**Purpose**: Fallback parser for banks that migrate from tables to divs  
**Features**:
- Detect div-based rate containers
- Extract field pairs from div structure
- Compatible with FieldStructureMixin

**Impact**: Handles complete structural migrations (table → div)

---

## SUCCESS METRICS

### Before Implementation (Current State):
- schema_change Error Rate: 15% of all collections
- Manual Fix Time: 6-8 hours/week
- Proactive Detection: 0%
- Auto-Recovery Rate: 0%

### After Phase 1 (Target):
- schema_change Error Rate: <10% (30% reduction)
- Manual Fix Time: 3-5 hours/week (40% reduction)
- Proactive Detection: 0% (Phase 2)
- Auto-Recovery Rate: 30-40% (multi-strategy catches variations)

---

## IMPLEMENTATION ORDER

### Step 1: Fuzzy Table Selection (30 min) ✅
- Enhance `HTMLTableAdapter._find_tables_fuzzy()`
- Add logging for strategy selection
- Test with Dashen, BOA fixtures

### Step 2: Multi-Strategy Parse Chain (45 min)
- Implement strategy fallback chain
- Test with adapters known to have schema changes (Hijra, Ahadu, Awash)

### Step 3: Enhanced Field Detection (30 min)
- Update `field_detection/detector.py` patterns
- Add regex for variations
- Test with all API adapters

### Step 4: Div Parser (60 min)
- Create `adapters/parsers/div_parser.py`
- Integrate with base adapter
- Test with Shabelle (already uses divs)

### Step 5: Integration Testing (30 min)
- Run Wave 2, 3, 4 adapter tests
- Verify backward compatibility
- Check no regressions

**Total Estimated Time**: 3-4 hours

---

## ROLLOUT PLAN

### Immediate (Today):
1. ✅ Implement fuzzy table selection
2. ✅ Enhanced field detection patterns
3. ✅ Test with existing fixtures

### Tomorrow:
4. Multi-strategy parsing chain
5. Div parser fallback
6. Full regression testing

### Day 3:
7. Deploy to production
8. Monitor collection runs
9. Track schema_change error rate

---

## TESTING STRATEGY

### Unit Tests:
- Test fuzzy selector with various HTML structures
- Test field detection with variations
- Test div parser with Shabelle fixture

### Integration Tests:
- Run existing test suites (Wave 2, 3, 4)
- Test against live bank sites (safe read operations)
- Compare results with current implementation

### Monitoring:
- Add logging for strategy selection
- Track which strategies succeed per bank
- Alert on new failure patterns

---

## BACKWARD COMPATIBILITY

All changes maintain 100% backward compatibility:
- ✅ Module-level wrapper functions unchanged
- ✅ Existing adapter implementations still work
- ✅ No breaking changes to public APIs
- ✅ Tests pass without modification

---

## NEXT STEPS AFTER PHASE 1

### Phase 2 (Week 2-3):
- Daily health checks (2 AM cron job)
- Schema change analyzer
- Adaptive strategy selection

### Phase 3 (Month 2-3):
- GPT-4 fallback parser pilot
- ML-based pattern learning
- Structure-agnostic extraction

---

**Status**: IN PROGRESS  
**Started**: October 23, 2026  
**Expected Completion**: October 24, 2026  
**Owner**: Exchange Rate System Team
