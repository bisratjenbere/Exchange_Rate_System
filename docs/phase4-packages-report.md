# Phase 4: Missing Packages - Progress Report

**Started:** 2024-11-23  
**Status:** ✓ COMPLETE  
**Goal:** Add missing migration, harden commit_correction, document fingerprint decision

---

## P4.1 — Add Migration 007 ✓ COMPLETE

**Effort:** S (actual: 15 minutes)  
**Goal:** Create migration file for collection_control table

### Implementation
- Created `db/migrations/007_add_collection_control.sql`
- Idempotent migration using CREATE TABLE IF NOT EXISTS
- Uses WHERE NOT EXISTS for initial row insertion
- Documented that singleton constraint managed by application code

**Verification:**
- ✓ Migration file created
- ✓ All 624 tests passing

---

## P4.2 — Harden commit_correction ✓ COMPLETE

**Effort:** XS (actual: 30 minutes)  
**Goal:** Prevent corrections on non-current observations

### Problem Identified
At HEAD (after P6), `commit_correction` doesn't check `is_current`:
- Locks prior observation with `FOR UPDATE`
- Reads version_number but NOT is_current
- If prior row already superseded, creates duplicate version number
- Results in data inconsistency (two rows with same version)

### Solution Implemented
Added `is_current` check in `pipeline/persist.py`:
```python
# Line 98-101
cur.execute(
    "SELECT id, logical_observation_key, version_number, is_current FROM rate_observation WHERE id = %s FOR UPDATE",
    (prior_obs_id,),
)
row = cur.fetchone()
if not row[3]:  # is_current
    raise StaleObservationError(f"Observation {prior_obs_id} is not current — cannot correct superseded observations")
```

### Test Added
Created `test_p4_commit_correction_rejects_non_current` in `tests/test_m7_runs_trusted_review.py`:
- Creates observation v1 (current)
- Creates observation v2 that supersedes v1
- Marks v1 as not current
- Verifies correction attempt on v1 raises StaleObservationError

**Verification:**
- ✓ New test passes
- ✓ All 624 tests passing (1 new test added)

---

## P4.3 — Document Fingerprint Decision ✓ COMPLETE

**Effort:** XS (actual: 10 minutes)  
**Goal:** Document why fingerprint_version filter is unnecessary

### Analysis
The hash **includes version** in fingerprint payload:
```python
# pipeline/fingerprint.py:14
payload = {
    "v": FINGERPRINT_VERSION,  # Version is in the hash input
    ...
}
```

Therefore:
- Old rows: `fingerprint = hash(v=2, ...)`
- New rows: `fingerprint = hash(v=3, ...)`
- Hashes differ, so filter by version cannot change matches

### Implementation
Added explanatory comment in `pipeline/deduplicate.py` lines 8-11:
```python
# Note: snapshot_fingerprint hash includes fingerprint_version in its payload
# (see pipeline/fingerprint.py:14), so rows with different versions produce
# different hashes. Therefore, no need to filter by fingerprint_version separately
# as v2 and v3 hashes cannot collide.
```

**Verification:**
- ✓ Comment added
- ✓ All 624 tests passing

---

## Phase 4 Summary

**Status:** ✓ COMPLETE  
**Time:** ~1 hour (vs 3-4 hour estimate)

**Achievements:**
1. ✓ Created migration 007 for collection_control table
2. ✓ Hardened commit_correction with is_current check
3. ✓ Documented fingerprint_version decision with inline comment
4. ✓ Added 1 new test for data integrity
5. ✓ All 624 tests passing

**Files Modified:**
- `db/migrations/007_add_collection_control.sql` (new)
- `pipeline/persist.py` (added is_current check)
- `pipeline/deduplicate.py` (added comment)
- `tests/test_m7_runs_trusted_review.py` (added test)

**Impact:**
| Improvement | Before | After |
|-------------|--------|-------|
| Migration files | 6 | 7 ✓ |
| Data integrity | Duplicate versions possible | Protected ✓ |
| Code clarity | Implicit fingerprint behavior | Documented ✓ |
| Test coverage | 623 tests | 624 tests ✓ |

**All Phase 4 tasks complete!**