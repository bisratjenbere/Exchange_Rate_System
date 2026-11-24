# `is_current` Ownership Plan

**Mode:** Plan (read-only, no source file modifications)

**Goal:** Make `pipeline/persist.py` the only module that writes `rate_observation.is_current`, without introducing a repository layer.

**Status:** Evidence-gathering complete, work packages defined

---

## Evidence Gathering

### 1. Behavioral Comparison: `api/app.py::review_decide` vs `review/workflow.py::decide_candidate`

#### `api/app.py::review_decide` (lines 270-350)

**Route:** `POST /review/decide`  
**Authentication:** None (no authentication decorator visible)  
**Parameters:** `obs_id[]` (list of int), `decision` ("approve" or "dismiss")

**Behavior:**

```python
# Line 270-278: Route definition, parameter parsing
@app.post("/review/decide")
def review_decide():
    obs_ids = request.form.getlist("obs_id", type=int)
    decision = request.form.get("decision")
    if not obs_ids or decision not in ("approve", "dismiss"):
        return jsonify({"error": "bad request"}), 400
```

**Transaction ownership:**
- Creates new connection: `conn = _conn()` (line 282)
- **Commits:** `conn.commit()` at line 338 (after all operations)
- **Rollbacks:** `conn.rollback()` in exception handler (line 342)
- **Connection management:** Returns conn to pool via `_put(conn, error=has_error)` (line 349)

**Decision logic for "approve":**

1. Fetches candidate observation (lines 284-290):
   ```python
   SELECT source_id, source_currency_code, category_id, effective_date
   FROM rate_observation WHERE id = %s
   ```

2. Fetches current active observation (lines 292-301):
   ```python
   SELECT id, effective_date
   FROM rate_observation
   WHERE source_id = %s AND source_currency_code = %s
     AND category_id IS NOT DISTINCT FROM %s AND is_current = TRUE
   ```

3. **Promotion logic** (lines 303-309):
   - Promotes if no active row exists
   - Promotes if `cand_eff_date >= active_eff_date`
   - **Does NOT promote** if `cand_eff_date < active_eff_date` (older date)
   - **Does NOT promote** if `cand_eff_date` is NULL but `active_eff_date` is set

4. **If promoting** (lines 311-320):
   - **Retires all current observations** for same (source, currency, category):
     ```python
     UPDATE rate_observation SET is_current = FALSE
     WHERE source_id = %s AND source_currency_code = %s
       AND category_id IS NOT DISTINCT FROM %s AND is_current = TRUE
     ```
   - **Promotes candidate:**
     ```python
     UPDATE rate_observation
     SET is_current = TRUE, change_review_status = 'new_publication'
     WHERE id = %s
     ```

5. **If NOT promoting** (lines 321-326):
   - Marks candidate as not current with status:
     ```python
     UPDATE rate_observation
     SET is_current = FALSE, change_review_status = 'new_publication'
     WHERE id = %s
     ```

**Decision logic for "dismiss":**
- Simply marks observations as dismissed (lines 327-333):
  ```python
  UPDATE rate_observation SET change_review_status = 'dismissed'
  WHERE id = ANY(%s)
  ```

**Key characteristics:**
- Handles multiple `obs_ids` in a loop
- **Does NOT use `commit_correction`** or versioning
- **Does NOT use `StaleObservationError`**
- **Does NOT use `decide_candidate` from review/workflow.py**
- Direct SQL manipulation of `is_current` and `change_review_status`
- Decisions: "approve" or "dismiss" (HTTP-level strings)

---

#### `review/workflow.py::decide_candidate` (full file)

**Function signature:**
```python
def decide_candidate(
    conn,
    candidate_id: int,
    decision: str,
    decided_by: str,
    decision_reason: str,
    record: Optional[AdapterRecord] = None,
    source_id: Optional[int] = None,
    run_id: Optional[int] = None,
    category_id: Optional[int] = None,
    fingerprint: Optional[str] = None,
    logical_key: Optional[str] = None,
    validation_status: Optional[ValidationStatus] = None,
    validation_messages: Optional[list] = None,
    fetched_at: Optional[datetime] = None,
) -> Optional[int]:
```

**Parameters:** `candidate_id`, `decision`, `decided_by`, `decision_reason`, plus optional correction parameters

**Transaction ownership:**
- **Accepts connection from caller** (does not create its own)
- **Commits internally:** `conn.commit()` at lines 73 and 76
- **No rollback handling** (expects caller to handle exceptions)

**Decision logic:**

1. Valid decisions: `{"confirmed_correction", "new_publication", "mapping_issue", "dismissed"}` (line 27)
   - **More granular than review_decide** ("approve"/"dismiss")

2. Fetches change_candidate record (lines 32-39):
   ```python
   SELECT observation_id, prior_version_id, source_id
   FROM change_candidate WHERE id=%s
   ```

3. Updates change_candidate metadata (lines 41-48):
   ```python
   UPDATE change_candidate SET
       status = %s, decision_reason = %s,
       decided_at = %s, decided_by = %s
   WHERE id = %s
   ```

4. Updates observation status (lines 50-53):
   ```python
   UPDATE rate_observation SET change_review_status=%s WHERE id=%s
   ```

5. **If decision is "confirmed_correction"** (lines 55-74):
   - Requires all correction parameters
   - **Calls `commit_correction`** (lines 60-71):
     - Creates new versioned observation
     - Locks prior observation with `FOR UPDATE`
     - Increments version number
     - Updates `is_current` flags (retires old, promotes new)
     - **Can raise `StaleObservationError`** if prior observation was superseded
   - Commits transaction (line 73)
   - Returns new observation ID

6. **For all other decisions** (lines 76-78):
   - Just commits the status update
   - Returns None

**Key characteristics:**
- Handles single `candidate_id`
- **Uses `commit_correction` for version-aware corrections**
- **Can raise `StaleObservationError`**
- Updates `change_candidate` table with audit trail
- Decisions: domain-level strings ("confirmed_correction", "new_publication", etc.)
- **Does NOT directly manipulate `is_current`** (delegates to `commit_correction`)

---

### Behavioral Differences Summary

| Aspect | `api/app.py::review_decide` | `review/workflow.py::decide_candidate` |
|--------|----------------------------|----------------------------------------|
| **Connection ownership** | Creates and commits | Accepts and commits |
| **Batch processing** | Yes (loops over `obs_ids`) | No (single candidate) |
| **Decision vocabulary** | "approve", "dismiss" | "confirmed_correction", "new_publication", "mapping_issue", "dismissed" |
| **Version numbering** | ❌ No versioning | ✅ Yes (via `commit_correction`) |
| **`commit_correction` usage** | ❌ Not used | ✅ Used for "confirmed_correction" |
| **`StaleObservationError`** | ❌ Not raised | ✅ Can be raised |
| **`is_current` writes** | ✅ Direct SQL (3 write sites) | ❌ Delegated to `commit_correction` |
| **`change_candidate` updates** | ❌ Not updated | ✅ Updated with audit trail |
| **Promotion logic** | Date comparison (promotes if newer) | Versioning-based (via correction) |
| **Audit trail** | Minimal (status only) | Full (`decided_by`, `decision_reason`, timestamp) |
| **Authentication** | None visible | Requires `decided_by` parameter |
| **Rollback handling** | ✅ Exception handler | ❌ Caller responsibility |
| **Multiple observations** | ✅ Loops over list | ❌ Single candidate |

**Critical incompatibility:** `review_decide` processes multiple observations in a loop with simple date-based promotion, while `decide_candidate` handles a single candidate with version-aware correction logic.

---

### 2. Transaction Ownership for Each `is_current` Write Site

Based on persistence-assessment.md and code analysis:

#### Write Site 1: `api/app.py:313` in `review_decide`
```python
UPDATE rate_observation SET is_current = FALSE
WHERE source_id = %s AND source_currency_code = %s
  AND category_id IS NOT DISTINCT FROM %s AND is_current = TRUE
```
- **Function:** `review_decide` (Flask route handler)
- **Transaction owner:** `review_decide` itself
- **Commit location:** Line 338 (`conn.commit()`)
- **Rollback:** Line 342 (exception handler)
- **Savepoint:** ❌ No savepoint used
- **Can run outside savepoint:** Yes (creates its own transaction)

#### Write Site 2: `api/app.py:321` in `review_decide`
```python
UPDATE rate_observation SET is_current = TRUE, change_review_status = 'new_publication'
WHERE id = %s
```
- **Function:** `review_decide` (Flask route handler)
- **Transaction owner:** `review_decide` itself
- **Commit location:** Line 338
- **Savepoint:** ❌ No savepoint used
- **Can run outside savepoint:** Yes

#### Write Site 3: `api/app.py:327` in `review_decide`
```python
UPDATE rate_observation SET is_current = FALSE, change_review_status = 'new_publication'
WHERE id = %s
```
- **Function:** `review_decide` (Flask route handler)
- **Transaction owner:** `review_decide` itself
- **Commit location:** Line 338
- **Savepoint:** ❌ No savepoint used
- **Can run outside savepoint:** Yes

---

#### Write Site 4: `pipeline/ingest.py:101` in `_process_one`
```python
UPDATE rate_observation
SET is_fallback = FALSE, is_current = TRUE
WHERE id = %s AND is_fallback = TRUE
```
- **Function:** `_process_one` (called from `ingest`)
- **Transaction owner:** `scheduler/runner.py::Scheduler.run_source` or caller
- **Commit location:** `scheduler/runner.py:259` (`conn.commit()` after ingest success)
- **Savepoint:** ✅ YES - runs inside `SAVEPOINT _ingest_sp` (line 41)
- **Rollback on error:** Line 49 (`ROLLBACK TO SAVEPOINT _ingest_sp`)
- **Can run outside savepoint:** No (always inside per-record savepoint)

**Note on line 101:** This UPDATE **writes to `is_current`** (sets it to TRUE) in addition to `is_fallback`.

---

#### Write Site 5: `pipeline/ingest.py:167` in `_process_one`
```python
UPDATE rate_observation SET is_current = FALSE WHERE id = %s
```
- **Function:** `_process_one`
- **Transaction owner:** Caller (scheduler)
- **Commit location:** `scheduler/runner.py:259`
- **Savepoint:** ✅ YES - inside `SAVEPOINT _ingest_sp`
- **Can run outside savepoint:** No

---

#### Write Site 6: `pipeline/ingest.py:227` in `_retire_older_current`
```python
UPDATE rate_observation SET is_current = FALSE
WHERE source_id = %s AND source_currency_code = %s
  AND category_id IS NOT DISTINCT FROM %s AND is_current = TRUE
```
- **Function:** `_retire_older_current` (called from `_process_one`)
- **Transaction owner:** Caller (scheduler via ingest)
- **Commit location:** `scheduler/runner.py:259`
- **Savepoint:** ✅ YES (inherits from caller's savepoint)
- **Can run outside savepoint:** No (called only from within savepoint)

---

#### Write Site 7: `pipeline/ingest.py:245` in `_retire_prior_fallback_observations`
```python
UPDATE rate_observation SET is_current = FALSE
WHERE source_id = %s AND source_currency_code = %s AND is_current = TRUE
  AND is_fallback = TRUE AND (effective_date IS NULL OR effective_date < %s)
```
- **Function:** `_retire_prior_fallback_observations` (fallback path)
- **Transaction owner:** Caller (scheduler via ingest)
- **Commit location:** `scheduler/runner.py:259`
- **Savepoint:** ✅ YES (inherits from caller's savepoint)
- **Can run outside savepoint:** No

---

#### Write Site 8: `pipeline/ingest.py:258` in `_retire_prior_fallback_observations`
```python
UPDATE rate_observation SET is_current = FALSE
WHERE source_id = %s AND source_currency_code = %s AND is_current = TRUE
  AND category_id IS NOT DISTINCT FROM %s
  AND (effective_date IS NULL OR effective_date < %s)
```
- **Function:** `_retire_prior_fallback_observations` (non-fallback path)
- **Transaction owner:** Caller (scheduler via ingest)
- **Commit location:** `scheduler/runner.py:259`
- **Savepoint:** ✅ YES
- **Can run outside savepoint:** No

---

#### Write Site 9: `pipeline/persist.py:30` in `insert_observation` (INSERT)
```python
INSERT INTO rate_observation (..., is_current, ...) VALUES (..., %s, ...)
```
- **Function:** `insert_observation`
- **Transaction owner:** Caller (various: ingest, review workflow, etc.)
- **Commit location:** Caller-dependent (scheduler, review, manual scripts)
- **Savepoint:** Varies (YES when called from ingest, NO from review workflow)
- **Can run outside savepoint:** Yes (designed as reusable function)

---

#### Write Site 10: `pipeline/persist.py:109` in `commit_correction` (INSERT)
```python
INSERT INTO rate_observation (..., is_current, ...) VALUES (..., FALSE, ...)
```
- **Function:** `commit_correction` (always inserts with `is_current = FALSE` initially)
- **Transaction owner:** Caller (review workflow)
- **Commit location:** `review/workflow.py:73` (inside `decide_candidate`)
- **Savepoint:** ❌ No savepoint
- **Can run outside savepoint:** Yes

---

#### Write Site 11: `pipeline/persist.py:152` in `commit_correction`
```python
UPDATE rate_observation SET is_current = FALSE WHERE id = %s
```
- **Function:** `commit_correction` (retires prior observation)
- **Transaction owner:** Caller (review workflow)
- **Commit location:** `review/workflow.py:73`
- **Savepoint:** ❌ No savepoint
- **Can run outside savepoint:** Yes

---

#### Write Site 12: `pipeline/persist.py:156` in `commit_correction`
```python
UPDATE rate_observation SET is_current = TRUE WHERE id = %s
```
- **Function:** `commit_correction` (promotes new corrected observation)
- **Transaction owner:** Caller (review workflow)
- **Commit location:** `review/workflow.py:73`
- **Savepoint:** ❌ No savepoint
- **Can run outside savepoint:** Yes

---

#### Write Site 13: `scheduler/runner.py:563` in `_expire_stale_fallback_current`
```python
UPDATE rate_observation SET is_current = FALSE
WHERE source_id = %s AND is_fallback = TRUE AND is_current = TRUE
  AND effective_date < CURRENT_DATE - %s
```
- **Function:** `_expire_stale_fallback_current` (expires old fallback observations)
- **Transaction owner:** `Scheduler.run_source`
- **Commit location:** `scheduler/runner.py:259`
- **Savepoint:** ❌ No (runs after ingest completes, outside savepoint loop)
- **Can run outside savepoint:** Yes

---

#### Write Site 14: `scheduler/runner.py:572` in `_expire_stale_fallback_current`
```python
UPDATE rate_observation SET is_current = FALSE
WHERE source_id = %s AND is_current = TRUE
  AND effective_date < CURRENT_DATE - INTERVAL '7 days'
  AND EXISTS (...)
```
- **Function:** `_expire_stale_fallback_current`
- **Transaction owner:** `Scheduler.run_source`
- **Commit location:** `scheduler/runner.py:259`
- **Savepoint:** ❌ No
- **Can run outside savepoint:** Yes

---

### Transaction Ownership Summary

| Write Site | File:Line | Function | Savepoint? | Transaction Owner | Commit Location |
|------------|-----------|----------|------------|-------------------|-----------------|
| 1 | api/app.py:313 | review_decide | ❌ | review_decide | app.py:338 |
| 2 | api/app.py:321 | review_decide | ❌ | review_decide | app.py:338 |
| 3 | api/app.py:327 | review_decide | ❌ | review_decide | app.py:338 |
| 4 | ingest.py:101 | _process_one | ✅ | Scheduler.run_source | runner.py:259 |
| 5 | ingest.py:167 | _process_one | ✅ | Scheduler.run_source | runner.py:259 |
| 6 | ingest.py:227 | _retire_older_current | ✅ | Scheduler.run_source | runner.py:259 |
| 7 | ingest.py:245 | _retire_prior_fallback | ✅ | Scheduler.run_source | runner.py:259 |
| 8 | ingest.py:258 | _retire_prior_fallback | ✅ | Scheduler.run_source | runner.py:259 |
| 9 | persist.py:30 | insert_observation | Varies | Caller | Caller |
| 10 | persist.py:109 | commit_correction | ❌ | decide_candidate | workflow.py:73 |
| 11 | persist.py:152 | commit_correction | ❌ | decide_candidate | workflow.py:73 |
| 12 | persist.py:156 | commit_correction | ❌ | decide_candidate | workflow.py:73 |
| 13 | runner.py:563 | _expire_stale_fallback | ❌ | Scheduler.run_source | runner.py:259 |
| 14 | runner.py:572 | _expire_stale_fallback | ❌ | Scheduler.run_source | runner.py:259 |

**Key insight:** Sites 4-8 (ingest.py) always run inside savepoints. Sites 1-3, 9-14 can run outside savepoints.

---

### 3. Line 101 of `pipeline/ingest.py`

**Full context (lines 95-112):**

```python
        if not is_fallback:
            if record.effective_date is not None:
                _retire_prior_fallback_observations(conn, source_id, record.source_currency_code, category_id, record.effective_date, is_fallback=False)
            if existing_id is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE rate_observation
                           SET is_fallback = FALSE,
                               is_current = TRUE
                           WHERE id = %s AND is_fallback = TRUE""",
                        (existing_id,)
                    )
        result.duplicates += 1
        return
```

**Analysis:**

**Line 101:** `UPDATE rate_observation SET is_fallback = FALSE, is_current = TRUE`

**Does it write `is_current`?** ✅ **YES**

This UPDATE sets **two columns**:
1. `is_fallback = FALSE` (clears fallback flag)
2. `is_current = TRUE` (promotes observation to current)

**Context:** This is the "duplicate promotion" path. When a non-fallback observation arrives that matches an existing fallback observation by fingerprint, the existing fallback row is promoted to non-fallback and marked current.

**Condition:** Only executes when:
- `not is_fallback` (incoming record is non-fallback)
- `existing_id is not None` (duplicate of existing observation)
- Existing row has `is_fallback = TRUE` (WHERE clause)

**Write count impact:** This is write site #4 in the evidence table above.

---

### 4. Existing Test Coverage

#### Tests for `api/app.py::review_decide`
**Result:** ❌ **No tests found**

Searched for:
- `review_decide`
- `def test.*review.*decide`

**Coverage:** 0% - No Flask test client tests exercising the `/review/decide` endpoint.

---

#### Tests for `review/workflow.py::decide_candidate`
**Result:** ✅ **3 tests found in `tests/test_m7_runs_trusted_review.py`**

1. **Line 419:** `test_review_dismissed_candidate`
   - Tests `decide_candidate` with `decision="dismissed"`
   - Verifies change_candidate status and observation status update

2. **Line 459:** `test_review_confirmed_correction_via_workflow`
   - Tests `decide_candidate` with `decision="confirmed_correction"`
   - Verifies `commit_correction` is called and new versioned observation created

3. **Line 528:** `test_p2_confirmed_correction_rolls_back_candidate_on_error`
   - Tests rollback behavior when `commit_correction` raises ValueError
   - Uses mocking to simulate failure

**Coverage:** Good for `decide_candidate`, covers happy paths and error handling.

---

#### Tests for retirement helpers

##### `_retire_older_current`
**Result:** ❌ **No dedicated tests**

Implicitly tested through integration tests (ingestion), but no isolated unit test.

---

##### `_retire_prior_fallback_observations`
**Result:** ✅ **1 test in `tests/test_fallback_guardrails.py`**

**Line 512:** `test_p4_fallback_caller_does_not_retire_non_fallback_row`
- Tests that fallback caller (`is_fallback=True`) only retires fallback rows
- Verifies non-fallback rows are left untouched
- **Directly imports and calls** `_retire_prior_fallback_observations`

**Coverage:** Narrow - only tests fallback path, not non-fallback path.

---

##### `_expire_stale_fallback_current`
**Result:** ✅ **2 tests in `tests/test_fallback_guardrails.py`**

1. **Line 427:** Implicit test in `test_fallback_ttl_expiry`
   - **Directly imports and calls** `_expire_stale_fallback_current`
   - Tests that old fallback observations are expired

2. **Line 447:** Another call in same test file
   - Tests expiry doesn't affect fresh observations

**Coverage:** Good for expiry logic.

---

### Test Coverage Summary

| Component | Tests | Coverage | Test Location |
|-----------|-------|----------|---------------|
| `api/app.py::review_decide` | ❌ 0 | None | - |
| `review/workflow.py::decide_candidate` | ✅ 3 | Good | test_m7_runs_trusted_review.py |
| `_retire_older_current` | ❌ 0 | Implicit only | - |
| `_retire_prior_fallback_observations` | ✅ 1 | Partial (fallback path) | test_fallback_guardrails.py |
| `_expire_stale_fallback_current` | ✅ 2 | Good | test_fallback_guardrails.py |

**Gap:** `review_decide` has no tests, making refactoring risky.

---

## Work Packages

### Package A: Ownership Ratchet Test

**Goal:** Create AST-based test that enforces `is_current` write site allowlist and shrinks over time.

**Files to create:**
- `tests/test_is_current_ownership.py`

**Files to touch:** None (new test only)

**Behavior change:** None (test-only)

**Risk:** Low (read-only test)

**Test approach:**

```python
# tests/test_is_current_ownership.py
"""
Ownership ratchet: enforce that is_current writes are centralized.

This test uses AST parsing to find all cur.execute() calls that write to
rate_observation.is_current and compares against an allowlist.

As write sites are moved to persist.py, remove them from ALLOWED_SITES.
The test fails if new write sites are added.
"""

import ast
from pathlib import Path

# Allowlist of (file, line, function) tuples
# Remove entries as they are migrated to persist.py
ALLOWED_SITES = {
    ("api/app.py", 313, "review_decide"),
    ("api/app.py", 321, "review_decide"),
    ("api/app.py", 327, "review_decide"),
    ("pipeline/ingest.py", 101, "_process_one"),
    ("pipeline/ingest.py", 167, "_process_one"),
    ("pipeline/ingest.py", 227, "_retire_older_current"),
    ("pipeline/ingest.py", 245, "_retire_prior_fallback_observations"),
    ("pipeline/ingest.py", 258, "_retire_prior_fallback_observations"),
    ("scheduler/runner.py", 563, "_expire_stale_fallback_current"),
    ("scheduler/runner.py", 572, "_expire_stale_fallback_current"),
    # pipeline/persist.py entries are allowed (target ownership module)
    ("pipeline/persist.py", 30, "insert_observation"),
    ("pipeline/persist.py", 109, "commit_correction"),
    ("pipeline/persist.py", 152, "commit_correction"),
    ("pipeline/persist.py", 156, "commit_correction"),
}

GOAL_OWNERSHIP_MODULE = "pipeline/persist.py"

def test_is_current_write_sites_allowlist():
    """Verify all is_current writes are in allowlist (ratchet test)"""
    # Use analyze_sql_queries.py logic to find write sites
    # Parse AST, find cursor.execute with is_current in SQL
    # Assert: found_sites <= ALLOWED_SITES
    # Assert: all non-persist.py sites are in allowlist
    pass

def test_ownership_progress_tracking():
    """Track progress toward single ownership"""
    non_persist_sites = {s for s in ALLOWED_SITES if s[0] != GOAL_OWNERSHIP_MODULE}
    
    # Current state: 10 non-persist.py write sites
    # Goal: 0 non-persist.py write sites
    assert len(non_persist_sites) <= 10, "is_current ownership has regressed!"
    
    print(f"Progress: {10 - len(non_persist_sites)}/10 write sites migrated to {GOAL_OWNERSHIP_MODULE}")
```

**Verification:**
1. Run test: `pytest tests/test_is_current_ownership.py -v`
2. Test should pass with current state (10 non-persist.py sites)
3. Test should fail if new write site added outside allowlist
4. Test should pass with fewer sites as migration proceeds

**Rollback:** Delete test file (no source code changed)

---

### Package B: Characterization Tests + `review_decide` Migration

**Goal:** Add Flask test client tests for `review_decide`, then refactor it to call `decide_candidate`.

**Files to create:**
- `tests/test_review_api.py` (new Flask test client tests)

**Files to modify:**
- `api/app.py` (refactor `review_decide` to call `decide_candidate`)

**Behavior change:** Internal (same HTTP API, different implementation)

**Risk:** Medium (changes production API endpoint)

#### Step B1: Characterization Tests (safe)

Create `tests/test_review_api.py`:

```python
"""
Characterization tests for /review/decide API endpoint.

These tests document current behavior before refactoring review_decide
to call review/workflow.py::decide_candidate.
"""

import pytest
from api.app import app

@pytest.fixture
def client():
    """Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def db():
    """Database connection for setup"""
    from tests.db_utils import get_conn, reset_schema, apply_migrations
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()

def test_review_decide_approve_promotes_newer_observation(client, db):
    """POST /review/decide with decision=approve promotes observation if newer"""
    # Setup: Create source, insert fallback observation (current)
    # Insert new non-fallback observation (not current, newer date)
    # POST /review/decide with decision=approve, obs_id=[new_obs_id]
    # Assert: new observation is current, old observation is not current
    pass

def test_review_decide_approve_does_not_promote_older(client, db):
    """POST /review/decide does not promote observation with older effective_date"""
    # Setup: Current observation (Oct 25), candidate observation (Oct 20)
    # POST /review/decide with decision=approve, obs_id=[candidate_id]
    # Assert: candidate is NOT current (older date)
    # Assert: original observation remains current
    pass

def test_review_decide_approve_promotes_when_no_active(client, db):
    """POST /review/decide promotes observation when no current exists"""
    # Setup: Observation with is_current=FALSE, no other current for same currency
    # POST /review/decide with decision=approve
    # Assert: observation is now current
    pass

def test_review_decide_dismiss_marks_dismissed(client, db):
    """POST /review/decide with decision=dismiss updates status"""
    # Setup: Observation with change_review_status='pending_review'
    # POST /review/decide with decision=dismiss
    # Assert: change_review_status = 'dismissed'
    # Assert: is_current unchanged
    pass

def test_review_decide_multiple_observations(client, db):
    """POST /review/decide handles multiple obs_ids"""
    # Setup: Multiple observations needing review
    # POST /review/decide with obs_id=[id1, id2, id3]
    # Assert: All processed correctly
    pass

def test_review_decide_bad_request_validation(client, db):
    """POST /review/decide validates input"""
    # Test missing obs_id
    # Test invalid decision value
    # Assert: 400 Bad Request
    pass

def test_review_decide_rollback_on_error(client, db):
    """POST /review/decide rolls back transaction on error"""
    # Setup: Create scenario that causes DB error mid-transaction
    # POST /review/decide
    # Assert: No partial changes committed
    pass
```

**Verification for B1:**
- Run tests: `pytest tests/test_review_api.py -v`
- All tests should pass against current `review_decide` implementation
- Tests document current behavior (date-based promotion, batch processing)

---

#### Step B2: Refactor `review_decide` (high risk)

**Decision needed:** How to map `review_decide` to `decide_candidate`?

**Option 1: Wrapper (preserves batch behavior)**
```python
# api/app.py
from review.workflow import decide_candidate

@app.post("/review/decide")
def review_decide():
    obs_ids = request.form.getlist("obs_id", type=int)
    decision = request.form.get("decision")
    if not obs_ids or decision not in ("approve", "dismiss"):
        return jsonify({"error": "bad request"}), 400
    
    # Map HTTP decisions to domain decisions
    domain_decision = "new_publication" if decision == "approve" else "dismissed"
    
    conn = None
    has_error = False
    try:
        conn = _conn()
        for oid in obs_ids:
            # Create change_candidate for each observation
            # (requires change_candidate record to exist - breaking change?)
            decide_candidate(
                conn=conn,
                candidate_id=oid,  # Assumes oid is change_candidate.id, NOT observation.id
                decision=domain_decision,
                decided_by="api_user",  # TODO: Extract from session/auth
                decision_reason="Approved via API",
            )
        # decide_candidate commits internally
    except Exception as exc:
        has_error = True
        # decide_candidate doesn't rollback, we need to
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error("POST /review/decide failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn, error=has_error)
    
    return jsonify({"status": "ok"}), 200
```

**Problem with Option 1:** 
- `review_decide` takes `obs_id` (rate_observation.id)
- `decide_candidate` takes `candidate_id` (change_candidate.id)
- **Breaking change** to API contract

**Option 2: Keep separate (reduce duplication only)**
```python
# api/app.py - keep review_decide as-is for now
# Move is_current manipulation to persist.py helper
# Call persist.py helpers instead of inline SQL

from pipeline.persist import retire_current_observations, promote_observation

@app.post("/review/decide")
def review_decide():
    # ... existing validation ...
    
    conn = None
    has_error = False
    try:
        conn = _conn()
        with conn.cursor() as cur:
            if decision == "approve":
                for oid in obs_ids:
                    # ... fetch candidate and active rows ...
                    
                    if promote:
                        # Call persist.py helper instead of inline SQL
                        retire_current_observations(conn, sid, cur_code, cat_id)
                        promote_observation(conn, oid, change_review_status='new_publication')
                    else:
                        # Call persist.py helper
                        demote_observation(conn, oid, change_review_status='new_publication')
            else:
                # dismiss path
                cur.execute(...)
        conn.commit()
    except Exception as exc:
        # ... existing error handling ...
```

**Option 3: Deprecate and replace (long-term)**
- Keep `review_decide` as-is (legacy)
- Create new `/review/decide_candidate` endpoint that calls `decide_candidate`
- Document `/review/decide` as deprecated
- Migrate UI to new endpoint over time

---

**Recommended approach: Option 2** (reduce duplication, preserve API)

**Rationale:**
1. `review_decide` and `decide_candidate` serve different use cases:
   - `review_decide`: Batch approval of multiple observations (simpler workflow)
   - `decide_candidate`: Single candidate with full correction workflow
2. Full consolidation requires breaking API changes
3. Option 2 achieves ownership goal (move SQL to persist.py) without breaking changes

**Files to modify:**
- `api/app.py`: Refactor to call persist.py helpers
- `pipeline/persist.py`: Add new helpers (see Package C)

**Behavior change:** None (internal refactor only)

**Verification for B2:**
- Run characterization tests: `pytest tests/test_review_api.py -v`
- All tests must still pass
- Run full test suite: `pytest tests/ -v`
- Manual testing of review UI

**Rollback:** 
1. `git revert` the api/app.py changes
2. Remove new helpers from persist.py (if not used elsewhere)

---

### Decisions Needed for Package B

**Decision 1: What to do with `review_decide`?**
- **Option A:** Keep as-is, move SQL to persist.py helpers (RECOMMENDED)
- **Option B:** Make it call `decide_candidate` (breaking change)
- **Option C:** Deprecate and create new endpoint (long-term)

**Recommended:** Option A

---

**Decision 2: Should review_decide require authentication?**
- **Current:** No auth visible in code
- **Risk:** Anyone can approve/dismiss observations
- **Options:**
  - Add auth decorator before refactoring
  - Leave as-is (assume deployed behind auth proxy)
  - Add TODO comment and track as separate security issue

**Recommended:** Add TODO comment, track as separate security issue (out of scope for ownership refactor)

---

**Decision 3: Handle difference in audit trail?**
- `decide_candidate` updates `change_candidate` with `decided_by`, `decided_at`, `decision_reason`
- `review_decide` does not update `change_candidate` at all

**Options:**
- **Option A:** Keep as-is (different workflows, different audit needs)
- **Option B:** Enhance `review_decide` to update `change_candidate` if record exists

**Recommended:** Option A (preserve current behavior)

---

### Package C: Move Retirement Helpers to `persist.py`

**Goal:** Move `_retire_older_current`, `_retire_prior_fallback_observations`, `_expire_stale_fallback_current` from their current locations to `pipeline/persist.py`.

**Files to modify:**
- `pipeline/persist.py` (add 3 functions)
- `pipeline/ingest.py` (import and call from persist.py)
- `scheduler/runner.py` (import and call from persist.py)
- `api/app.py` (import and call from persist.py, if doing Option 2 from Package B)

**Behavior change:** None (identical SQL, identical transaction behavior)

**Risk:** Low (pure code motion)

#### Step C1: Add functions to `persist.py`

```python
# pipeline/persist.py

def retire_current_observations(
    conn,
    source_id: int,
    currency_code: str,
    category_id: Optional[int]
) -> int:
    """
    Mark all current observations as not current for given criteria.
    
    Returns count of retired observations.
    
    Equivalent to ingest.py::_retire_older_current but accepts any source/currency/category.
    Used when promoting a new observation to current status.
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_observation
               SET is_current = FALSE
               WHERE source_id = %s
                 AND source_currency_code = %s
                 AND category_id IS NOT DISTINCT FROM %s
                 AND is_current = TRUE""",
            (source_id, currency_code, category_id),
        )
        return cur.rowcount


def retire_prior_fallback_observations(
    conn,
    source_id: int,
    currency_code: str,
    category_id: Optional[int],
    effective_date,
    is_fallback: bool = False
) -> int:
    """
    Retire fallback observations with older effective dates.
    
    If is_fallback=True (fallback caller): only retires is_fallback=TRUE rows.
    If is_fallback=False (non-fallback caller): retires fallback rows AND
        same-category non-fallback rows with older effective_date.
    
    Returns count of retired observations.
    
    Moved from pipeline/ingest.py::_retire_prior_fallback_observations
    """
    if effective_date is None:
        return 0
    
    with conn.cursor() as cur:
        if is_fallback:
            # Fallback caller: retire only prior fallback rows
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = FALSE
                   WHERE source_id = %s
                     AND source_currency_code = %s
                     AND is_current = TRUE
                     AND is_fallback = TRUE
                     AND (effective_date IS NULL OR effective_date < %s)""",
                (source_id, currency_code, effective_date),
            )
        else:
            # Non-fallback caller: retire fallback + same-category non-fallback
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = FALSE
                   WHERE source_id = %s
                     AND source_currency_code = %s
                     AND is_current = TRUE
                     AND category_id IS NOT DISTINCT FROM %s
                     AND (effective_date IS NULL OR effective_date < %s)""",
                (source_id, currency_code, category_id, effective_date),
            )
        return cur.rowcount


def expire_stale_fallback_current(conn, source_id: int) -> int:
    """
    Expire stale fallback observations for a source.
    
    Two expiry rules:
    1. Fallback observations older than FALLBACK_TTL_DAYS
    2. Any observation older than 7 days if newer (3-day) observations exist
    
    Returns count of expired observations.
    
    Moved from scheduler/runner.py::_expire_stale_fallback_current
    """
    # Import constant from scheduler
    from scheduler.runner import FALLBACK_TTL_DAYS
    
    expired_count = 0
    with conn.cursor() as cur:
        # Rule 1: Expire old fallback observations
        cur.execute(
            """UPDATE rate_observation
               SET is_current = FALSE
               WHERE source_id = %s
                 AND is_fallback = TRUE
                 AND is_current = TRUE
                 AND effective_date < CURRENT_DATE - %s""",
            (source_id, FALLBACK_TTL_DAYS),
        )
        expired_count += cur.rowcount
        
        # Rule 2: Expire any old observation if fresh ones exist
        cur.execute(
            """UPDATE rate_observation
               SET is_current = FALSE
               WHERE source_id = %s
                 AND is_current = TRUE
                 AND effective_date < CURRENT_DATE - INTERVAL '7 days'
                 AND EXISTS (
                     SELECT 1 FROM rate_observation
                     WHERE source_id = %s
                       AND is_current = TRUE
                       AND effective_date >= CURRENT_DATE - INTERVAL '3 days'
                 )""",
            (source_id, source_id),
        )
        expired_count += cur.rowcount
    
    return expired_count


def promote_observation(
    conn,
    observation_id: int,
    change_review_status: Optional[str] = None
) -> None:
    """
    Mark observation as current, optionally updating review status.
    
    Used by review workflows to promote an observation after approval.
    Does NOT retire other current observations - caller must do that first.
    """
    with conn.cursor() as cur:
        if change_review_status:
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = TRUE, change_review_status = %s
                   WHERE id = %s""",
                (change_review_status, observation_id),
            )
        else:
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = TRUE
                   WHERE id = %s""",
                (observation_id,),
            )


def demote_observation(
    conn,
    observation_id: int,
    change_review_status: Optional[str] = None
) -> None:
    """
    Mark observation as not current, optionally updating review status.
    
    Used by review workflows to demote an observation after decision.
    """
    with conn.cursor() as cur:
        if change_review_status:
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = FALSE, change_review_status = %s
                   WHERE id = %s""",
                (change_review_status, observation_id),
            )
        else:
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = FALSE
                   WHERE id = %s""",
                (observation_id,),
            )
```

---

#### Step C2: Update callers

**pipeline/ingest.py:**
```python
# Remove local definitions of _retire_older_current, _retire_prior_fallback_observations
# Add imports
from pipeline.persist import (
    retire_current_observations,
    retire_prior_fallback_observations,
)

# Update call sites:
# Line 227: _retire_older_current(conn, ...) 
#   becomes: retire_current_observations(conn, ...)

# Lines 95, 185, etc: _retire_prior_fallback_observations(conn, ...)
#   becomes: retire_prior_fallback_observations(conn, ...)
```

**scheduler/runner.py:**
```python
# Remove local definition of _expire_stale_fallback_current
# Add import
from pipeline.persist import expire_stale_fallback_current

# Update call sites:
# Line 258: _expire_stale_fallback_current(conn, source_id)
#   becomes: expire_stale_fallback_current(conn, source_id)
```

**api/app.py** (if doing Package B Option 2):
```python
# Add imports
from pipeline.persist import (
    retire_current_observations,
    promote_observation,
    demote_observation,
)

# Replace inline SQL with function calls (lines 311-328)
```

---

**Behavior change:** None (identical SQL and transaction semantics)

**Verification for C:**
1. Run full test suite: `pytest tests/ -v`
2. Specifically verify:
   - `tests/test_fallback_guardrails.py` (tests that import retirement helpers)
   - `tests/test_m7_runs_trusted_review.py` (integration tests)
3. Check imports updated correctly:
   ```bash
   grep "_retire_older_current" pipeline/ingest.py  # Should be 0 matches
   grep "retire_current_observations" pipeline/ingest.py  # Should find imports and calls
   ```

**Rollback:**
1. `git revert` the changes
2. Restore local function definitions in ingest.py and runner.py

---

### Package D: INSERT Constant for `insert_observation` and `commit_correction`

**Goal:** Extract the INSERT statement SQL into a constant, use named parameters to reduce duplication between `insert_observation` and `commit_correction`.

**Files to modify:**
- `pipeline/persist.py` (refactor INSERT statements)

**Behavior change:** None (identical SQL, different structure)

**Risk:** Low (internal refactor with same logic)

#### Approach

**Current state:** Two large INSERT statements with duplicated column lists:
- `insert_observation` (line 30): Full INSERT with all parameters
- `commit_correction` (line 109): Nearly identical INSERT with slight differences

**Differences between the two INSERTs:**
1. `insert_observation`: `is_current` from parameter
2. `commit_correction`: `is_current = FALSE` (hardcoded), `identity_status = 'confirmed'`, `change_review_status = 'confirmed_correction'`

**Proposed solution:**

```python
# pipeline/persist.py

# INSERT statement template with named parameters
_RATE_OBSERVATION_INSERT_SQL = """
INSERT INTO rate_observation (
    source_id, collection_run_id, category_id,
    currency_code, source_currency_code, currency_name,
    buying_rate, selling_rate, source_rate_text, source_excerpt,
    quote_currency_code, unit_multiplier,
    effective_date, effective_date_basis,
    fetched_at, snapshot_fingerprint, fingerprint_version,
    version_number, is_current, identity_status,
    validation_status, validation_messages,
    change_review_status, logical_observation_key,
    supersedes_id, is_fallback
) VALUES (
    %(source_id)s, %(run_id)s, %(category_id)s,
    %(currency_code)s, %(source_currency_code)s, %(currency_name)s,
    %(buying_rate)s, %(selling_rate)s, %(source_rate_text)s, %(source_excerpt)s,
    %(quote_currency_code)s, %(unit_multiplier)s,
    %(effective_date)s, %(effective_date_basis)s,
    %(fetched_at)s, %(fingerprint)s, %(fingerprint_version)s,
    %(version_number)s, %(is_current)s, %(identity_status)s,
    %(validation_status)s, %(validation_messages)s,
    %(change_review_status)s, %(logical_key)s,
    %(supersedes_id)s, %(is_fallback)s
) RETURNING id
"""

def insert_observation(
    conn,
    record: AdapterRecord,
    source_id: int,
    run_id: int,
    category_id: Optional[int],
    fingerprint: str,
    logical_key: Optional[str],
    identity_status: IdentityStatus,
    validation_status: ValidationStatus,
    validation_messages: list,
    fetched_at: datetime,
    version_number: Optional[int],
    is_current: bool,
    change_review_status: ChangeReviewStatus = ChangeReviewStatus.NOT_REQUIRED,
    supersedes_id: Optional[int] = None,
    is_fallback: bool = False,
) -> int:
    params = {
        'source_id': source_id,
        'run_id': run_id,
        'category_id': category_id,
        'currency_code': normalize_currency_code(record.source_currency_code),
        'source_currency_code': record.source_currency_code,
        'currency_name': record.currency_name,
        'buying_rate': record.buying_rate,
        'selling_rate': record.selling_rate,
        'source_rate_text': record.source_rate_text,
        'source_excerpt': json.dumps(record.raw_excerpt) if record.raw_excerpt else None,
        'quote_currency_code': record.quote_currency_code,
        'unit_multiplier': record.unit_multiplier,
        'effective_date': record.effective_date,
        'effective_date_basis': record.effective_date_basis,
        'fetched_at': fetched_at,
        'fingerprint': fingerprint,
        'fingerprint_version': FINGERPRINT_VERSION,
        'version_number': version_number,
        'is_current': is_current,
        'identity_status': identity_status.value,
        'validation_status': validation_status.value,
        'validation_messages': json.dumps(validation_messages) if validation_messages else None,
        'change_review_status': change_review_status.value,
        'logical_key': logical_key,
        'supersedes_id': supersedes_id,
        'is_fallback': is_fallback,
    }
    
    with conn.cursor() as cur:
        cur.execute(_RATE_OBSERVATION_INSERT_SQL, params)
        return cur.fetchone()[0]


def commit_correction(
    conn,
    prior_obs_id: int,
    record: AdapterRecord,
    source_id: int,
    run_id: int,
    category_id: Optional[int],
    fingerprint: str,
    logical_key: str,
    validation_status: ValidationStatus,
    validation_messages: list,
    fetched_at: datetime,
) -> int:
    with conn.cursor() as cur:
        # ... existing locking and version logic ...
        
        # Reuse INSERT with specific parameters for correction
        params = {
            'source_id': source_id,
            'run_id': run_id,
            'category_id': category_id,
            'currency_code': normalize_currency_code(record.source_currency_code),
            'source_currency_code': record.source_currency_code,
            'currency_name': record.currency_name,
            'buying_rate': record.buying_rate,
            'selling_rate': record.selling_rate,
            'source_rate_text': record.source_rate_text,
            'source_excerpt': json.dumps(record.raw_excerpt) if record.raw_excerpt else None,
            'quote_currency_code': record.quote_currency_code,
            'unit_multiplier': record.unit_multiplier,
            'effective_date': record.effective_date,
            'effective_date_basis': record.effective_date_basis,
            'fetched_at': fetched_at,
            'fingerprint': fingerprint,
            'fingerprint_version': FINGERPRINT_VERSION,
            'version_number': new_version,
            'is_current': False,  # Correction-specific: initially FALSE
            'identity_status': 'confirmed',  # Correction-specific
            'validation_status': validation_status.value,
            'validation_messages': json.dumps(validation_messages) if validation_messages else None,
            'change_review_status': 'confirmed_correction',  # Correction-specific
            'logical_key': logical_key,
            'supersedes_id': prior_obs_id,
            'is_fallback': False,  # Corrections are never fallback
        }
        
        cur.execute(_RATE_OBSERVATION_INSERT_SQL, params)
        new_id = cur.fetchone()[0]
        
        # ... existing is_current manipulation ...
        demote_observation(conn, prior_obs_id)
        promote_observation(conn, new_id)
    
    return new_id
```

**Benefits:**
1. Single source of truth for column list
2. Schema changes require updating only one place
3. Named parameters make it clear what each value represents
4. Easier to verify correctness (no counting positions)

**Verification for D:**
1. Run full test suite: `pytest tests/ -v`
2. All 623 tests must pass
3. Check SQL execution logs (if available) to verify identical queries
4. Manual smoke test: Run scheduler, verify observations inserted correctly

**Rollback:** `git revert` the persist.py changes

---

## Summary Table

| Package | Files Touched | Behavior Change | Risk | Verification | Rollback Cost |
|---------|---------------|-----------------|------|--------------|---------------|
| A | 1 new | None (test) | Low | Run test | Delete file |
| B1 | 1 new | None (test) | Low | Run tests | Delete file |
| B2 | 1 modified | Internal | Medium | Tests + manual | Git revert |
| C | 3 modified | None | Low | Full suite | Git revert |
| D | 1 modified | None | Low | Full suite | Git revert |

---

## Migration Order (Recommended)

1. **Package A** (ratchet test) - Establishes baseline, prevents regression
2. **Package B1** (characterization tests) - Documents current API behavior
3. **Package C** (move helpers) - Reduces scatter, keeps transaction semantics
4. **Package D** (INSERT constant) - Reduces duplication in persist.py
5. **Package B2** (refactor review_decide) - Optional, can be deferred

**After B2:** 10 non-persist.py write sites → 3 (api/app.py lines 313, 321, 327)
**After C:** 3 non-persist.py write sites → 0 (all in persist.py)

---

## Open Questions

### Question 1: What is the long-term plan for `api/app.py::review_decide`?

**Options:**
- **A:** Keep as separate workflow (batch approval), centralize SQL only
- **B:** Deprecate in favor of `decide_candidate` (requires UI changes)
- **C:** Enhance to use `decide_candidate` with API adapter layer

**Recommended:** A (defer B/C to separate effort)

---

### Question 2: Should we enforce single commit point?

**Current:** Both `decide_candidate` and `review_decide` call `conn.commit()` internally.

**Alternative:** Have all persist.py functions accept transactions but NOT commit, leave commit to top-level caller (scheduler, API handler).

**Tradeoff:**
- **Pro:** More explicit transaction boundaries, easier to compose operations
- **Con:** Requires changing all callers, more refactoring risk

**Recommended:** Leave as-is (commit remains in workflow/API layer)

---

### Question 3: Should persist.py have a "retire and promote" atomic helper?

**Use case:** Retirement + promotion always happen together (90% of cases).

**Proposed:**
```python
def replace_current_observation(
    conn,
    source_id: int,
    currency_code: str,
    category_id: Optional[int],
    new_observation_id: int,
    change_review_status: Optional[str] = None
) -> None:
    """
    Atomically retire current observation and promote new one.
    
    Equivalent to:
        retire_current_observations(conn, source_id, currency_code, category_id)
        promote_observation(conn, new_observation_id, change_review_status)
    """
    retire_current_observations(conn, source_id, currency_code, category_id)
    promote_observation(conn, new_observation_id, change_review_status)
```

**Recommended:** Add in Package C as convenience helper (reduces caller complexity)

---

## Completion Criteria

**Package A:**
- ✅ `tests/test_is_current_ownership.py` exists
- ✅ Test passes with 10 non-persist.py write sites
- ✅ Test fails if new write site added

**Package B:**
- ✅ `tests/test_review_api.py` exists with 7+ characterization tests
- ✅ All tests pass against current code
- ✅ (B2 optional) `review_decide` calls persist.py helpers
- ✅ (B2 optional) All characterization tests still pass

**Package C:**
- ✅ `retire_current_observations` in persist.py
- ✅ `retire_prior_fallback_observations` in persist.py
- ✅ `expire_stale_fallback_current` in persist.py
- ✅ All callers updated (ingest.py, runner.py)
- ✅ All 623 tests pass
- ✅ Ratchet test shows 0-3 non-persist.py write sites

**Package D:**
- ✅ `_RATE_OBSERVATION_INSERT_SQL` constant defined
- ✅ `insert_observation` uses named parameters
- ✅ `commit_correction` uses named parameters
- ✅ All 623 tests pass

**Final state:**
- ✅ All `is_current` writes in `pipeline/persist.py` or via its functions
- ✅ Ratchet test passes with 0 non-persist.py write sites (excluding potential api/app.py if B2 deferred)
- ✅ No behavior changes (all original tests pass)

---

**Plan complete. Ready for implementation.**
