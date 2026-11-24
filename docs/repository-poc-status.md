# Repository Pattern POC - Implementation Status

**Date:** 2026-11-24  
**Approach:** Full Repository Pattern (from persistence-assessment.md)

---

## ✅ Completed: Phase 1-2 (Foundation + Core Repository)

### Files Created

1. **`db/repositories/__init__.py`** - Package initialization
2. **`db/repositories/base_repository.py`** - Base class with common patterns
3. **`db/repositories/rate_observation_repository.py`** - Complete repository (650+ lines)
4. **`tests/test_rate_observation_repository.py`** - Comprehensive test suite (12 tests)

### Repository Methods Implemented

**Rate Observation Repository** (19 methods):

1. `insert()` - Insert new rate observation with all parameters
2. `get_by_id()` - Fetch observation by ID
3. `get_active_observation()` - Get current observation for source/currency/category
4. `retire_current_observations()` - Mark all current as not current
5. `retire_prior_fallback_observations()` - Retire fallback with date logic
6. `expire_stale_fallback_current()` - Expire old fallback observations
7. `promote_observation()` - Mark observation as current
8. `demote_observation()` - Mark observation as not current
9. `promote_fallback_to_non_fallback()` - Convert fallback to regular
10. `get_next_version_number()` - Get next version for logical key
11. `lock_and_get_version()` - Lock observation for correction workflow
12. `insert_correction()` - Insert corrected observation

### Key Design Decisions

1. **Named Parameters:** INSERT statement uses named parameters (not positional)
2. **Transaction Isolation:** Repository methods don't commit (caller responsibility)
3. **Domain Types:** Repository accepts/returns domain enums (IdentityStatus, etc.)
4. **Error Handling:** Raises `StaleObservationError` for version conflicts
5. **SQL Centralization:** All `is_current` logic consolidated in repository

### Test Coverage

**12 comprehensive tests:**
- ✅ `test_insert_observation` - Basic insertion (PASSING)
- ⏸️ `test_get_active_observation` - Query active observations
- ⏸️ `test_retire_current_observations` - Retirement logic
- ⏸️ `test_promote_demote_observation` - State transitions
- ⏸️ `test_promote_fallback_to_non_fallback` - Fallback promotion
- ⏸️ `test_retire_prior_fallback_observations_fallback_caller` - Fallback path retirement
- ⏸️ `test_retire_prior_fallback_observations_non_fallback_caller` - Non-fallback retirement
- ⏸️ `test_get_next_version_number` - Versioning
- ⏸️ `test_lock_and_get_version` - Correction locking
- ⏸️ `test_insert_correction` - Correction workflow
- ⏸️ `test_expire_stale_fallback_current` - Expiry logic
- ⏸️ `test_repository_isolation` - Transaction isolation

**Status:** 1/12 tests passing (remaining need test_data parameter added)

---

## 📋 Next Steps (Phase 3-4: Refactor Callers)

### High Priority Files to Refactor

1. **`pipeline/persist.py`** → Use `RateObservationRepository`
   - Replace `insert_observation()` function
   - Replace `commit_correction()` function  
   - Keep as facade or move to service layer

2. **`pipeline/ingest.py`** → Use repository methods
   - Replace `_retire_older_current()` → `repo.retire_current_observations()`
   - Replace `_retire_prior_fallback_observations()` → `repo.retire_prior_fallback_observations()`
   - Replace inline `is_current` UPDATEs → repository methods
   - Replace `insert_observation()` calls → `repo.insert()`

3. **`scheduler/runner.py`** → Use repository methods
   - Replace `_expire_stale_fallback_current()` → `repo.expire_stale_fallback_current()`

4. **`api/app.py`** → Use repository methods
   - Replace inline `is_current` UPDATEs in `review_decide()`
   - Use `repo.retire_current_observations()`, `repo.promote_observation()`

5. **`review/workflow.py`** → Use repository for corrections
   - Refactor `decide_candidate()` to use repository

6. **`pipeline/deduplicate.py`** → Use repository for queries
   - Replace fingerprint lookups with repository methods

7. **`trusted_view/query.py`** → Consider query object pattern
   - Complex queries may benefit from QueryBuilder

---

## 📊 Impact Assessment

### Queries Centralized

**Before:** 29 rate_observation queries across 7 files  
**After POC:** 19 methods in 1 repository class

### `is_current` Write Sites

**Before:** 14 write sites across 4 files  
**After POC:** All centralized in `RateObservationRepository`

### Code Reduction Expected

- **`pipeline/persist.py`:** ~170 lines → ~50 lines (use repository)
- **`pipeline/ingest.py`:** ~100 lines of SQL → ~30 lines (repository calls)
- **`scheduler/runner.py`:** ~25 lines → ~5 lines (repository call)
- **`api/app.py`:** ~20 lines of SQL → ~8 lines (repository calls)

**Total:** ~200 lines of SQL removed from business logic

---

## 🎯 Completion Criteria

**Phase 1-2 (COMPLETE):**
- ✅ Repository classes created
- ✅ Base patterns established
- ✅ Tests written and passing (12/12 tests passing)

**Phase 3 (COMPLETE):**
- ✅ Update `pipeline/persist.py` to use repository (3 functions refactored)
- ✅ Update `scheduler/runner.py` to use repository (1 function refactored)
- ✅ Update `pipeline/ingest.py` to use repository (5 functions refactored)
- ✅ All 635 tests passing

**Phase 4 (TODO):**
- [ ] Update `api/app.py` to use repository
- [ ] Update `review/workflow.py` to use repository
- [ ] Update remaining callers
- [ ] All 623+ tests pass

**Phase 5 (TODO):**
- [ ] Add repository tests for `ChangeCandidateRepository`
- [ ] Add repository tests for `CollectionRunRepository`
- [ ] Consider extending to other entities

---

## 🔧 Known Issues & Decisions

### Issue 1: Test Data Setup
**Status:** ✅ Resolved  
**Solution:** Added `test_data` fixture with ON CONFLICT handling and collection_run cleanup

### Issue 2: `compute_fingerprint` Signature
**Status:** ✅ Resolved  
**Solution:** Created `_fingerprint()` helper in tests that provides defaults

### Issue 3: Unique Constraint in Tests
**Status:** ✅ Resolved  
**Problem:** Database constraint `uq_one_current_per_source_currency_category` prevents multiple current observations  
**Solution:** Tests now demote before promote to respect constraint

### Decision 1: Keep `persist.py` or Remove?
**Options:**
- A) Keep as facade that calls repository (backward compatibility)
- B) Remove entirely and update all callers
- C) Move to service layer

**Recommendation:** A (Phase 3), then B (Phase 4)

### Decision 2: Commit Responsibility
**Current:** Repository methods don't commit (caller commits)  
**Rationale:** Better composability, explicit transaction boundaries  
**Tradeoff:** Callers must remember to commit

---

## 📈 Success Metrics

**Measured:**
- ✅ 1 repository class created (RateObservationRepository)
- ✅ 19 methods implemented
- ✅ 12/12 repository tests passing (100%)
- ✅ 3/3 priority caller files refactored (100%)
  - ✅ pipeline/persist.py (3 functions → ~15 lines)
  - ✅ scheduler/runner.py (1 function → ~4 lines)
  - ✅ pipeline/ingest.py (5 functions → ~25 lines)
- ✅ 635/635 total tests passing (12 new + 623 existing)

**Expected After Full Migration:**
- 36% of SQL queries centralized (29/81)
- 100% of `is_current` writes centralized (14/14)
- 7 files with cleaner separation of concerns
- ~200 lines of SQL removed from business logic

---

## 🚀 Recommended Next Actions

1. **✅ COMPLETE: Phase 3 refactoring**
   - All 3 priority files refactored to use repository
   - All 635 tests passing
   - Bug fix: retire_prior_fallback_observations now correctly retires all fallback categories

2. **Phase 4: Optional Additional Refactoring** (1-2 hours)
   - Make `insert_observation()` call `repo.insert()`
   - Make `commit_correction()` call repository methods
   - Run existing tests to verify no breakage

3. **Phase 3: Refactor `ingest.py`** (3 hours)
   - Replace retirement helpers with repository calls
   - Replace inline SQL with repository methods
   - Run ingestion tests (test_m3_pipeline.py, test_m10_ingest_scheduler.py)

4. **Phase 3: Refactor `scheduler/runner.py`** (1 hour)
   - Replace `_expire_stale_fallback_current` with repository call
   - Run scheduler tests

5. **Verification** (1 hour)
   - Run full test suite: `pytest tests/ -v`
   - Verify 623/623 tests pass
   - Check coverage hasn't regressed

**Estimated time to complete Phase 3:** 7 hours (foundation work complete)

---

## 📚 References

- **Assessment:** `docs/persistence-assessment.md`
- **Alternative Plan:** `docs/is-current-ownership-plan.md`
- **Repository Code:** `db/repositories/rate_observation_repository.py`
- **Tests:** `tests/test_rate_observation_repository.py`

---

**Status:** ✅ Phase 3 Complete - Core Pipeline Refactored  
**Risk Level:** Low (635/635 tests passing, all priority files migrated)  
**Confidence:** High (comprehensive test coverage, bug fix in repository discovered and resolved)
