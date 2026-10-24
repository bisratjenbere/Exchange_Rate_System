# Bug Analysis: Adapter Parsing Failure for NIB, Hibret, and Zemen

**Date**: October 21, 2026  
**Reported By**: User  
**Severity**: CRITICAL - Banks with published rates are not being collected

## Problem Summary

Banks (NIB, Hibret, Zemen) have published Oct 21, 2026 exchange rates on their websites, but our system is **not capturing any data** from them. Collection runs show:
- HTTP Status: 200 (success)
- Records Found: 0
- Records Accepted: 0

## Root Cause Analysis

### Issue #1: Duplicate Function Definition Bug in `scheduler/runner.py`

**Location**: `scheduler/runner.py` lines 569 and 706

**Problem**: The `_check_schema()` function was defined TWICE:
1. Line 569: Correct version with `repo: RateSourceRepository = None` (handles both cases)
2. Line 706: Broken version with required `repo: RateSourceRepository` parameter (no default)

The second definition overwrote the first, causing the function to fail when called with `repo=None` from the backward-compatibility `run_source()` function.

**Impact**: Schema changes were NOT being detected, so when bank websites changed their HTML structure, our adapters continued using old parsing logic without raising alerts.

**Fix Applied**: Removed the duplicate function definition at line 706.

### Issue #2: HTML Structure Changed on Bank Websites

**Evidence**:
- NIB's schema fingerprint in DB: `eec4517a0b21af03...`
- Current website fingerprint: `40ce5d8853a5551a...` (DIFFERENT!)
- Manual adapter test: NIB adapter finds 9 records with correct Oct 21 date
- But first record shows: `currency=160.9994` (this is a RATE, not a currency code!)

**Conclusion**: The HTML table structure changed. The adapter expects currency code in `cells[1]`, but the actual data now has rate values in that position. The columns have shifted or been reordered.

### Issue #3: Fingerprint V2 Not Preventing Duplicates (Separate Issue - Already Fixed)

This was the original daily snapshot bug we fixed earlier. The fingerprint now includes `collection_date`, allowing one record per day even with unchanged rates.

## Current Status

### Working Banks (Have Oct 21 Data):
- CBE, NBE, Omo, Rammis, Anbesa, Oromia, Shabelle, Hijra, Addis, CBO

### Broken Banks (Website Changed, Adapters Failing):
- **NIB** (Nib International Bank) - Has Oct 21 on website, adapter parsing wrong columns
- **Zemen** (Zemen Bank) - Has Oct 21 on website, adapter returns 0 records  
- **Hibret** (Hibret Bank) - Currently shows Oct 20 data (not Oct 21), so this may be correct

### Other Banks (Not Yet Published Oct 21):
- 21 other banks haven't published afternoon rates yet

## Recommended Actions

### Immediate (High Priority):

1. **Fix NIB Adapter** (`adapters/nib/adapter.py`):
   - Inspect current HTML structure from https://www.nibbanksc.com/exchange-rate/
   - Update column mappings in `_parse_cash_txn()` and `_parse_weighted()`
   - Update schema fingerprint expectations
   - Test with live data

2. **Fix Zemen Adapter** (`adapters/zemen/adapter.py`):
   - Check if WordPress AJAX endpoint response structure changed
   - Test with live data from https://zemenbank.com/wp-admin/admin-ajax.php
   - Update parsing logic if needed

3. **Clear Old Fingerprints**:
   ```sql
   UPDATE rate_source 
   SET schema_fingerprint = NULL 
   WHERE adapter_key IN ('nib_html', 'zemen_ajax', 'hibret_html');
   ```

4. **Monitor Schema Change Alerts**:
   - After fix, the system should auto-accept new fingerprints on successful parse
   - Check `raw_capture` table for schema_change entries

### Medium Priority:

5. **Add Integration Tests** for schema change detection:
   - Test that duplicate `_check_schema()` doesn't happen again
   - Test that schema changes trigger raw_capture
   - Test that new fingerprints are auto-accepted after successful parse

6. **Review All Other Adapters**:
   - Check if any other banks have similar issues
   - Review adapters that returned 0 records today

### Low Priority:

7. **Improve Schema Change Monitoring**:
   - Add dashboard alert when schema_fingerprint changes
   - Log fingerprint mismatches even if parse succeeds
   - Track adapter version alongside schema fingerprint

## Technical Details

### Test Results:

**Manual NIB Adapter Test**:
```
HTTP Status: 200
Fetched: 151,431 bytes
Found: 9 records
Effective Date: 2026-10-21 ✓
BUT: currency=160.9994 (WRONG - this is a rate, not USD/EUR/GBP)
```

**Database Collection Runs**:
```
source_id=18 (NIB): records_found=0, records_accepted=0
source_id=17 (Hibret): records_found=10, records_accepted=0, records_flagged=10
source_id=58 (Zemen): records_found=0, records_accepted=0
```

### Code Changes Made:

**File**: `scheduler/runner.py`  
**Change**: Removed duplicate `_check_schema()` function definition at line 706  
**Status**: ✅ Fixed

## Next Steps

1. Investigate NIB's current HTML structure
2. Update NIB adapter column mappings
3. Investigate Zemen's JSON response
4. Test all three adapters with live data
5. Commit fixes
6. Run full collection
7. Verify Oct 21 data is captured

## Files to Review

- `adapters/nib/adapter.py` - Column mapping issue
- `adapters/zemen/adapter.py` - Zero records issue
- `adapters/hibret/adapter.py` - Verify correct (may just be slow to publish)
- `scheduler/runner.py` - Duplicate function fixed
- `pipeline/fingerprint.py` - Fingerprint V2 (already fixed separately)

## Lessons Learned

1. **Duplicate function definitions** are silent bugs that can mask critical failures
2. **Schema fingerprinting** is essential for detecting website changes
3. **Integration testing** should cover the full collection flow, not just adapters in isolation
4. **Manual testing** of adapters against live websites catches issues faster than waiting for scheduled runs
