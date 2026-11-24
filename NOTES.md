# Characterization Test Notes

## Wrong Assumptions Corrected

### 1. AdapterRecord Schema
**Assumed:** Fields like `currency`, `mid_rate`, `spread_percent`, `spread_birr`, effective_date_basis="published"

**Actually:** Only `source_currency_code`, `buying_rate`, `selling_rate`, `effective_date`, `effective_date_basis="source_published"`, `category`

**Why:** I didn't read domain/records.py before writing tests. The actual AdapterRecord is simpler than I expected.

### 2. Dry-Run Transaction Scope
**Assumed:** Dry-run mode rolls back EVERYTHING including the collection_run record

**Actually:** Dry-run rolls back observations but collection_run record IS created because `start_run()` is called BEFORE the dry_run check and commits immediately

**Why:** Didn't trace the transaction boundaries. The `start_run()` call at line 102 commits before the try block that contains the dry_run check at line 226.

**Bug Status:** CONFIRMED BUG - Dry-run mode leaves orphaned 'running' collection_run records. Test documents this behavior.

### 3. Schema Change Return Value
**Assumed:** Result dict has `schema_changed` key everywhere

**Actually:** `schema_changed` is only in the success path return dict (line 285) and dry_run return dict (line 236), NOT in failed/error paths

**Why:** Didn't check all exit paths. Schema change detection happens but isn't always reported in failed scenarios.

### 4. Database Schema - Column Names
**Assumed:** rate_observation table has `fingerprint` and direct fallback fields

**Actually:** Column is `snapshot_fingerprint`, and `is_fallback` was added in migration 003, not in base schema

**Why:** Didn't read migrations carefully. Need to check actual schema not assumed schema.

### 5. Failure Counter Threshold
**Assumed:** Test needed complex setup for threshold

**Actually:** Default ALERT_AFTER_CONSECUTIVE_FAILURES=3, and logic is straightforward at lines 456-476

**Why:** Over-complicated the test scenario. The actual logic is simpler than expected.

### 6. Category ID Population
**Assumed:** rate_category table is pre-populated in test database

**Actually:** Test fixtures need to seed categories using ON CONFLICT DO UPDATE pattern (see test_m7_runs_trusted_review.py::_seed_category)

**Why:** Didn't check how other tests handle category setup. Each test module must seed its own reference data.

### 7. Test Result Status Value
**Assumed:** recover_stuck_run would return something specific

**Actually:** Result status after recovering stuck run is normal "success" or "partial_success" - the recovery is a side effect, not reflected in return value

**Why:** Didn't check the actual return dict structure. The recover happens before start_run, so it doesn't affect the new run's result.

---

## Suspected Bugs Found During Test Writing

### 1. Stale-but-Valid Double Status (HIGH PRIORITY) ✅ CONFIRMED
**Location:** `scheduler/runner.py` lines 193-227

**Current Behavior:**
- When records are >3 days old but no fallback exists:
  1. Run is marked as `'failed'` with `error_code='stale_feed'` at line 184
  2. Records are THEN ingested anyway at line 198
  3. Run is updated AGAIN to `'success'` with same `error_code='stale_feed'` at line 202-212

**Why This Looks Wrong:**
- Contradictory: status='success' but error_code='stale_feed'
- Two `finish_run()` calls and two database commits for one logical operation
- Confusing for monitoring: was it a failure or success?
- Failure counter incremented even though records ARE retained

**Test:** `test_stale_records_retained_as_standing_rate()` - PASSES, pins this behavior

**Impact:** Monitoring dashboards likely show inflated failure rates because stale-but-retained runs count as failures initially.

**Suggested Fix (after refactoring):**
- Skip the initial finish_run('failed') call
- Go straight to success with error_code='stale_feed' and error_summary explaining retention
- OR use status='partial_success' to indicate data quality issue
- Only increment failure counter if records are NOT retained

---

### 2. Dry-Run Leaves Orphaned Runs (MEDIUM PRIORITY) ✅ CONFIRMED
**Location:** `scheduler/runner.py` line 102 (start_run), line 226 (dry_run check)

**Current Behavior:**
- Dry-run mode calls `start_run()` which creates collection_run record with status='running'
- Then rolls back observations but NOT the run record
- Result: Orphaned 'running' records accumulate in collection_run table

**Test:** `test_dry_run_rolls_back_all_changes()` - PASSES, documents this behavior

**Impact:** Database accumulates fake 'running' records that never finish. These may trigger stuck_run recovery later.

**Suggested Fix:**
- Check dry_run BEFORE calling start_run()
- OR have dry_run mode use a separate testing transaction that rolls back everything
- OR mark dry-run runs with a flag and exclude them from monitoring

---

### 3. Silent Failure in Raw Capture Storage (MEDIUM PRIORITY)
**Location:** `scheduler/runner.py` lines 276-279

**Current Behavior:**
```python
try:
    _store_raw_capture(conn, run_id, error_code, raw_content)
except Exception:
    pass  # Silent failure
```

**Why This Looks Wrong:**
- Raw captures are for forensics/debugging bank format changes
- If storage fails, we lose critical debugging data
- No log, no alert, no metric - failure is completely invisible
- Could mask serious issues (disk full, permissions, schema errors)

**Test:** `test_parse_error_attempts_raw_capture_even_if_it_fails()` - PASSES, pins this behavior

**Suggested Fix:**
- At minimum: log the exception at ERROR level
- Better: increment a "raw_capture_failures" counter metric
- Best: Add to run result dict so operators know data was lost: `{"raw_capture_failed": true}`

---

### 4. Expire Stale Fallback Logic Unclear (LOW PRIORITY)
**Location:** `scheduler/runner.py` line 267, function `_expire_stale_fallback_current()`

**Current Behavior:**
- Called as side effect after successful run
- Uses `FALLBACK_TTL_DAYS = 3` to expire old fallback observations
- No indication in return value that this happened
- If expiration fails, success is still reported

**Test:** `test_success_expires_stale_fallback_observations()` - PASSES, pins this behavior

**Why This Might Be Wrong:**
- Side effect is invisible to callers/monitoring
- Difficult to test/verify in production
- No way to detect if expiration logic breaks

**Suggested Fix:**
- Include expiration count in return dict: `{"fallback_expired_count": N}`
- Wrap in try/except and log failures
- Make it part of CollectionResult dataclass

---

## Test Coverage Improvement

### Before Characterization Tests
```
Name                 Stmts   Miss  Branch  BrPart  Cover
scheduler/runner.py    322     81     108      24    71%
```

### After Characterization Tests (9 new tests)
```
Name                 Stmts   Miss  Branch  BrPart  Cover
scheduler/runner.py    322     59     108      20    78%
```

**Improvement:**
- **+7% overall coverage** (71% → 78%)
- **-22 missed statements** (81 → 59)
- **-4 partially covered branches** (24 → 20)

### Coverage Gaps Filled

1. ✅ **Concurrent run conflict** (UniqueViolation handler, line 108-112)
2. ✅ **Stale-but-valid logic** (lines 169-227, confirmed double-status bug)
3. ✅ **Dry-run mode** (lines 226-240, confirmed orphaned run bug)
4. ✅ **Schema change detection** (line 215-217, raw capture storage)
5. ✅ **Expire stale fallback** (line 267, side effect testing)
6. ✅ **Parse error raw capture** (lines 276-279, silent failure)
7. ✅ **Alert threshold logic** (lines 456-476, failure counter)
8. ✅ **Recover stuck runs** (line 101, side effect before start)
9. ✅ **Zero records path** (lines 169-192, no ingestion verification)

### Still Uncovered Branches (20 partial branches remain)

From coverage report analysis, these branches are still not covered:
- Line 27: Exit path in `_fetch_with_retry` (early return on exception)
- Lines 33-34, 45, 51: Retry backoff logic branches
- Line 89: Source not found error path
- Lines 101-103: Circuit breaker fallback paths
- Lines 325-327: Generic exception classification variations
- Lines 355-379: `_try_af_fallback` internals (Addis Fortune fallback logic)
- Lines 416, 420, 430-431: Parsing error edge cases
- Lines 498-500, 511, 529-533: Fallback retry variations

**Next Priority for Coverage:** Circuit breaker + fallback logic testing
