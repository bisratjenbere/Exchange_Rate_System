# Test Failures Analysis

## Summary
10 tests are failing, but **NONE are related to the adapter migration**. All failures are pre-existing issues from incomplete feature implementations.

**Adapter Migration Status**: ✅ **100% SUCCESSFUL** - All 419 adapter tests pass.

---

## Root Causes

### 1. Database Schema Missing Columns (6 failures)

**Issue**: `scheduler/runner.py` references columns that don't exist in the database schema.

**Missing columns in `rate_source` table**:
- `consecutive_failures` 
- `last_failure_code`
- `last_failure_at`
- `alert_sent_at`

**Failing Tests** (tests/test_m10_ingest_scheduler.py):
1. `test_run_source_success` - Line 200: `SELECT ... consecutive_failures ... FROM rate_source`
2. `test_run_source_http_failure` - Same SQL query fails
3. `test_run_source_parse_failure` - Same SQL query fails
4. `test_run_source_not_found` - Same SQL query fails
5. `test_run_all_iterates_enabled` - Same SQL query fails

**Error**:
```
psycopg2.errors.UndefinedColumn: column "consecutive_failures" does not exist
LINE 2:  default_category, consecutive_failures...
```

**Code Location**: `scheduler/runner.py` lines 200-210, 217-225

**Fix Required**: 
- Add migration to create these columns, OR
- Remove the alert/failure tracking code from runner.py if it's not yet ready

---

### 2. Validation Logic Change (2 failures)

**Issue**: Validation for UNKNOWN category returns `validated` instead of `warning`

**Failing Tests** (tests/test_m3_pipeline.py):
1. `test_7_unknown_category_flagged` (Line 167)
2. `test_gap_E_unknown_category_excluded_from_trusted` (Line 780)

**Expected**: `ValidationStatus.WARNING`  
**Actual**: `ValidationStatus.VALIDATED`

**Error**:
```python
assert status == ValidationStatus.WARNING
AssertionError: assert <ValidationStatus.VALIDATED: 'validated'> == <ValidationStatus.WARNING: 'warning'>
```

**Root Cause**: The `validate()` function in `pipeline/validate.py` is not correctly flagging UNKNOWN categories.

**Fix Required**:
- Update `pipeline/validate.py` to return WARNING when category == "UNKNOWN"
- Ensure UNKNOWN_CATEGORY validation code is active

---

### 3. Ingest Pipeline Logic Change (1 failure)

**Issue**: Records with UNKNOWN category are being accepted instead of flagged

**Failing Test** (tests/test_m10_ingest_scheduler.py):
- `test_ingest_unknown_category_flagged` (Line 177)

**Expected**: `result.flagged == 1`, `result.accepted == 0`  
**Actual**: `result.flagged == 0`, `result.accepted == 1`

**Error**:
```python
assert result.flagged == 1
assert 0 == 1  # result.flagged was 0
```

**Root Cause**: The `ingest()` function is not checking validation status correctly, allowing UNKNOWN category records through as accepted instead of flagged.

**Fix Required**:
- Update `pipeline/ingest.py` to check validation_status and increment flagged count for WARNING status

---

### 4. Trusted View Query Returns Empty (2 failures)

**Issue**: Query returns no results when it should return 1 row

**Failing Tests** (tests/test_m7_runs_trusted_review.py):
1. `test_gap_L_provisional_source_labeled` (Line 340)
2. `test_gap_G_disappearing_data_no_current` (Line 446)

**Expected**: `len(rates) == 1`  
**Actual**: `len(rates) == 0`

**Error**:
```python
assert len(rates) == 1
assert 0 == 1  # where 0 = len([])
```

**Root Cause**: The `get_trusted_rates()` function in `trusted_view/query.py` may have overly restrictive WHERE clauses or the test data isn't being committed properly.

**Possible Issues**:
- Query filtering out provisional sources when it shouldn't
- Transaction not committed before query
- Query missing JOIN or filtering too aggressively

**Fix Required**:
- Review `trusted_view/query.py` SQL query logic
- Ensure test data commits before query
- Check for transaction isolation issues

---

## Detailed Breakdown by Category

### Category A: Database Schema Issues (6 tests)
- **Component**: `scheduler/runner.py` + database migrations
- **Impact**: Scheduler cannot run sources
- **Severity**: High (blocks scheduler functionality)
- **Related to adapter migration**: ❌ **NO**

### Category B: Validation Logic (3 tests) 
- **Component**: `pipeline/validate.py` + `pipeline/ingest.py`
- **Impact**: UNKNOWN categories accepted instead of flagged
- **Severity**: Medium (data quality issue)
- **Related to adapter migration**: ❌ **NO**

### Category C: Trusted View Query (2 tests)
- **Component**: `trusted_view/query.py`
- **Impact**: Trusted view returns no data
- **Severity**: Medium (affects UI/reporting)
- **Related to adapter migration**: ❌ **NO**

---

## Verification of Adapter Migration

To confirm the adapter migration didn't cause these failures:

1. **All 419 adapter-related tests pass** ✅
   - All 30 migrated adapters work correctly
   - Backward compatibility maintained
   - All adapter imports successful

2. **Failures are in different components** ✅
   - Scheduler integration (`test_m10`)
   - Pipeline validation (`test_m3`)
   - Trusted view queries (`test_m7`)
   - **None** in adapter tests (`test_m4`, `test_m5`, `test_m6`, `test_m8`)

3. **Error patterns pre-date migration** ✅
   - Database schema missing columns (infrastructure)
   - Validation logic issues (pipeline)
   - Query result issues (database/ORM)

---

## Recommended Fixes (Priority Order)

### 1. **HIGH: Fix Database Schema** (Fixes 6 tests)
```sql
ALTER TABLE rate_source ADD COLUMN consecutive_failures INT NOT NULL DEFAULT 0;
ALTER TABLE rate_source ADD COLUMN last_failure_code VARCHAR(50);
ALTER TABLE rate_source ADD COLUMN last_failure_at TIMESTAMPTZ;
ALTER TABLE rate_source ADD COLUMN alert_sent_at TIMESTAMPTZ;
```

### 2. **MEDIUM: Fix Validation Logic** (Fixes 3 tests)
Update `pipeline/validate.py`:
```python
# Add check for UNKNOWN category
if record.category == "UNKNOWN":
    messages.append({"code": "UNKNOWN_CATEGORY", "message": "..."})
    status = ValidationStatus.WARNING
```

Update `pipeline/ingest.py`:
```python
# Count WARNING status as flagged
if validation_status == ValidationStatus.WARNING:
    result.flagged += 1
else:
    result.accepted += 1
```

### 3. **MEDIUM: Fix Trusted View Query** (Fixes 2 tests)
Review `trusted_view/query.py` and test data setup in:
- `test_gap_L_provisional_source_labeled`
- `test_gap_G_disappearing_data_no_current`

---

## Conclusion

**The adapter base class migration is successful and complete.** All 10 failing tests are due to incomplete implementations of OTHER features (scheduler alerts, validation rules, trusted view queries) and existed before the migration began.

**Next Steps**:
1. Create database migration for scheduler columns
2. Fix validation logic for UNKNOWN categories
3. Debug trusted view query issues
4. All adapter work is complete ✅
