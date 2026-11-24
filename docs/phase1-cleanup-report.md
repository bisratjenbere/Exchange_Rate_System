# Phase 1: Cleanup - Progress Report

**Started:** 2024-11-23  
**Status:** In Progress

---

## P1.1 — Delete Dead Code ✓ COMPLETE

**Effort:** XS (actual: ~90 minutes including test fixes)  
**Files Modified:**
- `scheduler/runner.py` (-325 lines, now 585 lines)
- `tests/test_fallback_guardrails.py` (+54 lines - converted to Scheduler class)
- `tests/test_m10_ingest_scheduler.py` (+88 lines - converted to Scheduler class)

**Functions Deleted (8 total, 318 lines):**
1. `run_source` (standalone, lines 321-512) - 192 lines
2. `run_all` (standalone, lines 514-523) - 10 lines
3. `_load_source_old` (lines 588-601) - 14 lines
4. `_load_enabled_sources_old` (lines 603-614) - 12 lines
5. `_check_schema_old` (lines 616-627) - 12 lines
6. `_update_fingerprint_old` (lines 645-650) - 6 lines
7. `_update_last_success_old` (lines 652-657) - 6 lines
8. `_try_af_fallback_old` (lines 659-724) - 66 lines

**Additional Changes:**
- Inlined `_update_fingerprint_old` logic into `_check_schema` (6 lines added)
- Updated 7 test functions to use `Scheduler` class instead of standalone functions
- Fixed test mocking to work with new Scheduler architecture

**Verification:**
- ✓ No undefined names (`ruff --select F821`)
- ✓ All tests pass (623/623)
- ✓ File size reduced from 898 to 585 lines (-313 net lines)

**Key Test Updates:**
1. `test_zero_records_triggers_fallback_without_unique_violation` - Now uses Scheduler with mock registry and http client
2. `test_stale_feed_retained_when_no_fallback` - Same pattern
3. `test_run_source_success` - Mocks RequestsHttpClient class
4. `test_run_source_http_failure` - Updated for Scheduler architecture
5. `test_run_source_parse_failure` - Updated for Scheduler architecture
6. `test_run_source_not_found` - Simple Scheduler instantiation
7. `test_run_all_iterates_enabled` - Uses Scheduler.run_all
8. `test_zero_records_without_fallback_marks_run_failed` - Full mock stack

---

## P1.2 — Fix Unused Imports ⚠️ PARTIAL

**Target:** Auto-fix 92 F401 violations (unused imports)  
**Actual:** 59 violations found (down from 92 after P1.1 dead code removal)  
**Effort:** XS (20 minutes)

**Status:** Reviewed but not auto-fixed - many are intentional:

**Intentional imports (side-effects, should NOT be removed):**
- `infrastructure.env` (4 files) - Side-effect import that loads .env files
- Possibly others in adapters (many adapter imports flagged)

**Decision:** Defer F401 fixes to later phase. These need manual review to distinguish:
1. True unused imports (safe to remove)
2. Side-effect imports (must keep)
3. Re-exports in `__init__.py` files (must keep)
4. Forward references for type hints (may need `TYPE_CHECKING`)

**Current approach creates risk of breaking side-effect loading.**

**Tests:** ✓ 623/623 passing (no changes applied)

---

## P1.3 — Modernize Type Hints ✓ COMPLETE

**Target:** Auto-fix 141 UP045 violations (Optional[X] → X | None)  
**Actual:** 137 violations fixed  
**Effort:** XS (10 minutes)

**Changes Applied:**
- Replaced `Optional[X]` with `X | None` syntax (PEP 604)
- Affects 60+ files across adapters/, infrastructure/, pipeline/, scheduler/
- Modern Python 3.10+ union syntax

**Sample changes:**
```python
# Before
def _extract_date(self, text: str) -> Optional[date]:

# After  
def _extract_date(self, text: str) -> date | None:
```

**Verification:**
- ✓ All 137 violations fixed automatically
- ✓ 623/623 tests passing
- ✓ No regressions introduced

**Files Modified:** 60+ files (see git diff --stat)

---

## Summary

**Progress:** 2/3 tasks complete (P1.1 ✓, P1.2 ⚠️ deferred, P1.3 ✓)  
**Lines Removed:** 313 net from dead code (P1.1)  
**Type Hints Modernized:** 137 fixes (P1.3)  
**Tests:** 623/623 passing ✓  

**Next Steps:**
- P1.2 unused imports deferred - needs manual review for side-effects
- Ready for Phase 2: Refactoring

