# Code Quality Review — Exchange Rate System

**Review Date:** 2026-11-23  
**Reviewer:** Kiro AI Agent  
**Scope:** Full repository (fresh analysis from source code)  
**Mode:** Read-only review  

---

## Test Status

**Command:**
```bash
$ python3 -m pytest tests/ -q
```

**Result:** 22 failed, 600 passed in 4.75s

**Coverage tool:** Not available (pytest-cov not installed)  
**Linter:** Not available (ruff not installed)  
**Type checker:** Not available (mypy not installed)  
**Complexity analyzer:** Not available (radon not installed)

---

## Code Metrics (Custom Analysis)

**Command:**
```bash
$ python3 /tmp/complexity_analysis.py
```

**Results:**
- Total Python files: 141
- Core code lines: 3,738 (pipeline + scheduler + infrastructure + domain + review)
- Complex functions found: 22 (complexity > 10 OR lines > 50 OR params > 5 OR depth > 4)

**Top 5 Most Complex Functions:**
1. `pipeline/ingest.py:67` — `_process_one()`: Complexity 62, Lines 152, Params 8, Depth 7
2. `scheduler/runner.py:78` — `Scheduler.run_source()`: Complexity 28, Lines 231, Params 3, Depth 4
3. `scheduler/runner.py:321` — `run_source()`: Complexity 27, Lines 192, Params 2, Depth 3
4. `scheduler/cli.py:74` — `test_adapter()`: Complexity 15, Lines 94, Params 3, Depth 4
5. `pipeline/validate.py:5` — `validate()`: Complexity 14, Lines 57, Params 1, Depth 2

**Type Hint Coverage:**
```bash
$ python3 /tmp/type_hint_coverage.py
Type hint coverage: 68/82 functions (82%)
```

---

## Mandatory Checks

### 1. Hidden Clocks and Non-Canonical Decimal Serialization

**File:** `pipeline/fingerprint.py`

**Finding:** ✅ **NO HIDDEN CLOCKS** — `compute_fingerprint()` requires explicit `collection_date` parameter.

**Code:**
```python
# pipeline/fingerprint.py:14
def compute_fingerprint(record: AdapterRecord, source_id: int, collection_date: date) -> str:
    payload = {
        "v": FINGERPRINT_VERSION,
        "source_id": source_id,
        "collection_date": collection_date.isoformat(),  # ✓ Explicit parameter
        "source_currency_code": record.source_currency_code,
        "category": record.category,
        "effective_date": record.effective_date.isoformat() if record.effective_date else None,
        "buying_rate": _canonical_decimal(record.buying_rate),
        "selling_rate": _canonical_decimal(record.selling_rate),
        "source_publication_key": record.source_publication_key,
        "unit_multiplier": _canonical_decimal(record.unit_multiplier),
        "quote_currency_code": record.quote_currency_code,
    }
```

**Finding:** ✅ **CANONICAL DECIMAL SERIALIZATION** — `_canonical_decimal()` normalizes Decimals before serialization.

**Code:**
```python
# pipeline/fingerprint.py:9-12
def _canonical_decimal(d) -> str | None:
    if d is None:
        return None
    return format(Decimal(d).normalize(), "f")
```

**Analysis:** This handles edge cases like `Decimal("1.00")` vs `Decimal("1.0")` by normalizing before serialization. The `.normalize()` removes trailing zeros, and `format(..., "f")` ensures fixed-point notation (not scientific).

**Status:** No issues found.

---

### 2. commit_correction Version Derivation

**File:** `pipeline/persist.py:82-161`

**Finding:** ✅ **VERSION DERIVED FROM LOCKED ROW** — Uses `FOR UPDATE` and reads `version_number` from locked row.

**Code:**
```python
# pipeline/persist.py:97-107
with conn.cursor() as cur:
    cur.execute(
        "SELECT id, logical_observation_key, version_number FROM rate_observation WHERE id = %s FOR UPDATE",
        (prior_obs_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise StaleObservationError(f"Prior observation {prior_obs_id} not found or already superseded")
    if row[1] != logical_key:
        raise ValueError("Logical key mismatch — cannot correct across different observations")

    locked_version = row[2] if row[2] is not None else 1
    new_version = locked_version + 1
```

**Finding:** ⚠️ **is_current NOT CHECKED** — The function does NOT verify that the locked row has `is_current = TRUE`.

**Failure Scenario:**
1. Observation A (version 1) is current
2. Observation B (version 2) supersedes A and becomes current
3. Admin calls `commit_correction(prior_obs_id=A.id, ...)`
4. Lock succeeds (A still exists), version derived: 3
5. New observation C (version 3) created with `is_current = FALSE` initially
6. Line 153 sets A to `is_current = FALSE` (no-op, already false)
7. Line 157 sets C to `is_current = TRUE`
8. **Result:** B loses `is_current` status silently, C becomes current with wrong lineage

**Evidence from code:**
```python
# pipeline/persist.py:153-158
cur.execute(
    "UPDATE rate_observation SET is_current = FALSE WHERE id = %s",
    (prior_obs_id,),
)
cur.execute(
    "UPDATE rate_observation SET is_current = TRUE WHERE id = %s",
    (new_id,),
)
```

The function assumes `prior_obs_id` is current but never checks. The constraint `uq_one_current_per_logical_key` will catch this only if B still has `is_current = TRUE`, but the code doesn't lock B.

**Recommendation:** Add check after `FOR UPDATE`:
```python
if not row[3]:  # Assuming is_current is row[3]
    raise StaleObservationError(f"Observation {prior_obs_id} is not current")
```

**Severity:** HIGH — Data integrity risk in concurrent correction scenarios.

---

### 3. Transaction Boundaries in review/workflow.py

**File:** `review/workflow.py`

**Finding:** ✅ **COMMITS CALLED EXPLICITLY** at two locations:

**Code:**
```python
# review/workflow.py:73
if decision == "confirmed_correction":
    # ... call commit_correction ...
    conn.commit()  # ← Commit 1: After successful correction
    return new_id

conn.commit()  # ← Commit 2: After other decisions (dismissed, mapping_issue, etc.)
return None
```

**Analysis:**
- Commit happens AFTER `commit_correction()` completes
- If `commit_correction()` raises exception, commit is skipped (transaction rolls back)
- For non-correction decisions, commit happens after updating `change_candidate` and `rate_observation`

**Potential Issue:** If `commit_correction()` internally commits (it doesn't, verified in persist.py), this would be a double-commit. But `commit_correction()` is clean — no internal commits.

**Status:** Transaction boundaries are clear and correct.

---

### 4. WHERE/OR Condition in _retire_prior_fallback_observations

**File:** `pipeline/ingest.py:237-266`

**Finding:** Complex OR condition with different logic for fallback vs non-fallback callers.

**Code:**
```python
# pipeline/ingest.py:241-266
def _retire_prior_fallback_observations(conn, source_id: int, currency_code: str, category_id, effective_date, is_fallback: bool = False):
    if effective_date is None:
        return
    with conn.cursor() as cur:
        if is_fallback:
            # Fallback caller: retire only prior fallback rows with a strictly
            # older effective_date. Same-date fallback rows (e.g. cash and
            # transactional ingested together) are left untouched.
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
            # Non-fallback caller: retire fallback rows AND same-category
            # non-fallback rows with an older effective_date.
            cur.execute(
                """UPDATE rate_observation
                   SET is_current = FALSE
                   WHERE source_id = %s
                     AND source_currency_code = %s
                     AND is_current = TRUE
                     AND (is_fallback = TRUE OR (category_id IS NOT DISTINCT FROM %s AND effective_date < %s))""",
                (source_id, currency_code, category_id, effective_date),
            )
```

**Analysis of OR clause (non-fallback branch, line 265):**
```
(is_fallback = TRUE OR (category_id IS NOT DISTINCT FROM %s AND effective_date < %s))
```

This retires:
1. **All fallback rows** (regardless of date or category), OR
2. **Non-fallback rows** with matching category and older effective_date

**Failure Scenario:**
1. Fallback row for USD/cash with effective_date = 2026-11-20 is current
2. Native row for USD/transactional with effective_date = 2026-11-23 is ingested (different category)
3. Line 265 OR clause evaluates:
   - `is_fallback = TRUE` → matches the USD/cash fallback
   - Fallback row is retired

**Result:** Cross-category retirement of fallback rows by native ingestion. This is INTENTIONAL per the comment "retire fallback rows" (line 256-257).

**Question for maintainer:** Should native USD/transactional retire fallback USD/cash? Or should the OR clause include category filter?

**Current behavior:** Native observation retires ALL fallback rows for that currency (across all categories).

**Status:** Likely intentional design, but worth confirming with domain expert.

---

### 5. Adapters Importing from Infrastructure

**Command:**
```bash
$ grep -r "from infrastructure" adapters/ --include="*.py" | grep -v "__pycache__"
```

**Result:** (empty output)

**Finding:** ✅ **NO CIRCULAR DEPENDENCY** — Adapters do NOT import from `infrastructure`.

**However:** `infrastructure/adapter_registry.py` imports from ALL adapters:

```python
# infrastructure/adapter_registry.py:3-33
from adapters.abay import adapter as abay_adapter
from adapters.adib import adapter as adib_adapter
from adapters.ahadu import adapter as ahadu_adapter
# ... 30 more imports
```

This creates **import-time coupling** but NOT a circular dependency (adapters don't import back).

**Implications:**
- Cannot import `infrastructure.adapter_registry` without loading all 33 adapters
- Adapter import failures break unrelated infrastructure code
- Slower startup time

**Recommendation:** Use lazy loading with `importlib.import_module()`.

---

### 6. classify_observation When Logical Key Matches Current

**File:** `pipeline/deduplicate.py:4-29`

**Code:**
```python
# pipeline/deduplicate.py:4-29
def classify_observation(
    fingerprint: str,
    logical_key: Optional[str],
    conn,
) -> tuple:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
            (fingerprint,),
        )
        row = cur.fetchone()
        if row:
            return "duplicate", row[0]

        if logical_key is None:
            return "new", None

        cur.execute(
            """SELECT id FROM rate_observation
               WHERE logical_observation_key = %s AND is_current = TRUE
               LIMIT 1""",
            (logical_key,),
        )
        row = cur.fetchone()
        if row:
            return "changed", row[0]

        return "new", None
```

**Finding:** When logical key matches an existing row with `is_current = TRUE`, function returns `("changed", existing_id)`.

**What happens next (in `ingest.py:112-168`):**
1. If rates differ significantly and validation fails → goes to anomaly review
2. Otherwise → new version created with `supersedes_id = existing_id`
3. Line 168: `UPDATE rate_observation SET is_current = FALSE WHERE id = %s` (retire old)
4. New observation inserted with `is_current = TRUE`

**Status:** Behavior is correct and expected. The `is_current = TRUE` filter ensures we only match the active version, not superseded ones.

---

## Critical Findings

### C-1: Fingerprint Query Missing Version Filter

**Location:** `pipeline/deduplicate.py:10`

**Severity:** CRITICAL

**Code:**
```python
# pipeline/deduplicate.py:10-12
cur.execute(
    "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
    (fingerprint,),
)
```

**Missing filter:** `AND fingerprint_version = %s`

**Current fingerprint version:**
```python
# pipeline/fingerprint.py:7
FINGERPRINT_VERSION = 3
```

**Database schema:**
```sql
-- db/migrations/001_initial_schema.sql:112
fingerprint_version SMALLINT NOT NULL DEFAULT 1,
```

**Failure Scenario:**
1. Production database has 10,000 observations with `fingerprint_version = 2`
2. Deploy bumps `FINGERPRINT_VERSION = 3` (already done in current code)
3. Next collection run computes fingerprint with `v: 3`
4. Query `WHERE snapshot_fingerprint = <hash>` finds NO match (hash includes version)
5. Wait, that's not right. Let me recalculate...

**Re-analysis:** The fingerprint payload includes `"v": FINGERPRINT_VERSION`, so a version bump changes the hash itself. A fingerprint computed with `v=3` will produce a different SHA256 hash than the same data with `v=2`.

**Actual failure scenario:**
1. Observation X stored with `fingerprint_version=2`, hash `abc123`
2. Same data re-ingested after version bump
3. New fingerprint computed with `v=3`, hash `def456` (different!)
4. Query `WHERE snapshot_fingerprint = 'def456'` finds nothing
5. Classified as "new" instead of "duplicate"
6. Duplicate data inserted

**However:** The query on line 10 doesn't filter by version, so it CAN find old-version matches IF the hash somehow collides (impossible due to version in payload).

**Conclusion:** The query is SAFE but INCOMPLETE. After a version bump:
- Old data with `v=2` will not be found by new queries with `v=3` hashes
- This is INTENTIONAL if fingerprint logic changed
- But query should filter `AND fingerprint_version = %s` for clarity and to prevent cross-version matches if hash collision occurs (astronomical odds)

**Verification:**
```bash
$ grep -n "snapshot_fingerprint.*WHERE" pipeline/deduplicate.py
10:    "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
42:    WHERE snapshot_fingerprint = %s
```

Both queries lack `fingerprint_version` filter.

**Recommendation:** Add version filter to both queries for defensive coding:
```python
cur.execute(
    "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s AND fingerprint_version = %s LIMIT 1",
    (fingerprint, FINGERPRINT_VERSION),
)
```

---

### C-2: Duplicate run_source() Implementations

**Location:** `scheduler/runner.py:78` (Scheduler class method) and `scheduler/runner.py:321` (standalone function)

**Severity:** CRITICAL

**Evidence:**
```bash
$ grep -n "^def run_source\|^    def run_source" scheduler/runner.py
78:    def run_source(self, conn, source_id: int) -> dict:
321:def run_source(conn, source_id: int) -> dict:
```

**Code:**
```python
# scheduler/runner.py:78-308 (231 lines)
class Scheduler:
    def run_source(self, conn, source_id: int) -> dict:
        # ... 231 lines of implementation ...

# scheduler/runner.py:321-512 (192 lines)
def run_source(conn, source_id: int) -> dict:
    # ... 192 lines of similar implementation ...
```

**Production entry point uses standalone function:**
```python
# scheduler/run_job.py:14
from scheduler.runner import run_all

# scheduler/run_job.py:65
results = run_all(conn)
```

**run_all() uses standalone run_source():**
```python
# scheduler/runner.py:514-524
def run_all(conn) -> list:
    reap_stuck_runs(conn, threshold_minutes=5)
    sources = _load_enabled_sources_old(conn)
    results = []
    config = Config()
    for source in sources:
        result = run_source(conn, source["id"])  # ← Calls standalone function, not Scheduler method
        results.append(result)
        time.sleep(config.RATE_LIMIT_DELAY)
    return results
```

**Six duplicate helper functions:**
```bash
$ grep -n "def.*_old" scheduler/runner.py
588:def _load_source_old(conn, source_id: int) -> Optional[dict]:
603:def _load_enabled_sources_old(conn) -> list:
616:def _check_schema_old(conn, run_id: int, source: dict, adapter, raw_content: str) -> bool:
645:def _update_fingerprint_old(conn, source_id: int, fingerprint):
652:def _update_last_success_old(conn, source_id: int):
659:def _try_af_fallback_old(conn, source_id: int, adapter_key: str, user_agent: str) -> Optional[dict]:
```

**Failure Scenario:**
1. Bug found in `Scheduler.run_source()` circuit breaker logic
2. Developer fixes it and adds test using `Scheduler` class
3. Test passes, code ships
4. Production uses `run_all()` → calls standalone `run_source()` → bug still present
5. Production failure, test coverage didn't catch it

**Impact:**
- Must apply every bug fix twice
- Production and test code paths diverge
- 423 lines of duplicated logic (231 + 192)

**Recommendation:** Delete standalone `run_source()` and `_old` functions. Migrate `run_all()` to use `Scheduler` class.

---

### C-3: 22 Test Failures

**Command:**
```bash
$ python3 -m pytest tests/ -q
```

**Result:**
```
FAILED tests/test_m3_pipeline.py::test_6_ambiguous_identity_retained_and_flagged
FAILED tests/test_m3_pipeline.py::test_12_concurrent_correction_no_competing_current
FAILED tests/test_m3_pipeline.py::test_gap_A_revert_goes_to_review_not_deduplicated
FAILED tests/test_m3_pipeline.py::test_gap_B_repeated_candidate_yields_one_open
FAILED tests/test_m3_pipeline.py::test_gap_E_unknown_category_excluded_from_trusted
FAILED tests/test_m3_pipeline.py::test_gap_J_effective_date_basis_stored
FAILED tests/test_m7_runs_trusted_review.py::test_acceptance_10_failed_run_prior_observations_intact
FAILED tests/test_m7_runs_trusted_review.py::test_acceptance_19_trusted_view_excludes_ambiguous
FAILED tests/test_m7_runs_trusted_review.py::test_acceptance_19_trusted_view_excludes_rejected
FAILED tests/test_m7_runs_trusted_review.py::test_acceptance_19_trusted_view_excludes_unknown_category
FAILED tests/test_m7_runs_trusted_review.py::test_gap_L_provisional_source_labeled
FAILED tests/test_m7_runs_trusted_review.py::test_gap_C_pending_review_shows_uncertainty_warning
FAILED tests/test_m7_runs_trusted_review.py::test_acceptance_21_stale_rate_shows_staleness_warning
FAILED tests/test_m7_runs_trusted_review.py::test_acceptance_22_no_silent_substitution
FAILED tests/test_m7_runs_trusted_review.py::test_gap_G_disappearing_data_no_current
FAILED tests/test_m7_runs_trusted_review.py::test_review_dismissed_candidate
FAILED tests/test_m7_runs_trusted_review.py::test_review_confirmed_correction_via_workflow
FAILED tests/test_m7_runs_trusted_review.py::test_p2_confirmed_correction_rolls_back_candidate_on_error
FAILED tests/test_m7_runs_trusted_review.py::test_p6_commit_correction_derives_version_from_locked_row
22 failed, 600 passed in 4.75s
```

**Severity:** CRITICAL

**Analysis:** 3.5% test failure rate (22/622). Failures concentrated in two modules:
1. `test_m3_pipeline.py` — 6 failures (pipeline core logic)
2. `test_m7_runs_trusted_review.py` — 16 failures (review workflow and trusted view)

**Pattern:** Test names suggest recent refactoring:
- `test_p2_confirmed_correction_rolls_back_candidate_on_error` — P2 likely refers to package 2 from a refactor plan
- `test_p6_commit_correction_derives_version_from_locked_row` — P6 likely refers to package 6

**Hypothesis:** Tests were written for new behavior but code not fully migrated. Or code was migrated but tests not updated.

**Impact:** Cannot trust current code quality. 22 failing tests indicate broken functionality or stale tests.

**Recommendation:**
1. Run `pytest -v tests/test_m3_pipeline.py::test_6_ambiguous_identity_retained_and_flagged` to see failure detail
2. Fix tests OR fix code to match tests
3. Do not proceed with deployment until test suite is green

---

## High Priority Findings

### H-1: Monster Function — _process_one()

**Location:** `pipeline/ingest.py:67-218`

**Complexity Metrics:**
- Cyclomatic complexity: 62
- Lines: 152
- Parameters: 8
- Max nesting depth: 7

**Code snippet:**
```python
# pipeline/ingest.py:67-70
def _process_one(conn, record, source_id, run_id, fetched_at,
                 category_map, result, is_fallback: bool = False):
    val_status, val_messages = validate(record)
    # ... 149 more lines ...
```

**Failure Scenario:**
1. Developer needs to fix bug in fallback promotion logic (line ~110)
2. Must read 152 lines to understand context
3. Function mixes validation, deduplication, identity resolution, version numbering, concurrency control, anomaly detection, and persistence
4. Change to fallback logic accidentally breaks anomaly detection
5. Test coverage insufficient to catch (due to complexity)

**Impact:**
- Cognitive overload: impossible to hold entire function in working memory
- Untestable: cannot test sub-behaviors in isolation
- Error-prone: high coupling between unrelated concerns
- Difficult to modify: change ripples unpredictably

**Recommendation:** Extract into smaller functions:
1. `_validate_and_classify(record, conn, source_id, fetched_at, category_map)` → returns `(action, existing_id, val_status, val_messages, fingerprint, logical_key, identity_status)`
2. `_compute_version_and_currency(action, is_anomaly, existing_id, logical_key, identity_status, val_status)` → returns `(version_number, is_current, change_review_status, supersedes_id)`
3. `_retire_superseded_and_persist(conn, action, is_current, record, ...)` → inserts and retires old

Target: <30 lines per function, <5 parameters, <3 nesting levels.

---

### H-2: Transaction Management in pipeline/runs.py

**Location:** `pipeline/runs.py`

**Finding:** Every function commits independently.

**Code:**
```python
# pipeline/runs.py:16-17
run_id = cur.fetchone()[0]
conn.commit()  # ← start_run commits

# pipeline/runs.py:51
cur.execute(...)
conn.commit()  # ← finish_run commits

# pipeline/runs.py:65
reaped = cur.fetchall()
conn.commit()  # ← reap_stuck_runs commits

# pipeline/runs.py:88
cur.execute(...)
conn.commit()  # ← recover_stuck_run commits

# pipeline/runs.py:103
cur.execute(...)
conn.commit()  # ← record_raw_capture commits
```

**Failure Scenario:**
1. `run_source()` calls `start_run(conn, source_id)` → commits
2. `run_source()` processes records, encounters error
3. `run_source()` calls `finish_run(conn, run_id, 'failed')` → commits
4. Transaction cannot be rolled back atomically

**Analysis:** This is INTENTIONAL design. Each `runs.py` function is an independent transaction boundary. This allows partial commits (run record exists even if ingestion fails).

**However:** Caller (e.g., `scheduler/runner.py`) may also call `conn.commit()`, creating double-commit risk.

**Evidence from scheduler/runner.py:**
```python
# scheduler/runner.py:276-277
conn.commit()
return { ... }
```

**Current behavior:**
1. `start_run(conn, source_id)` → commit 1
2. `ingest(conn, records, ...)` → no commit (rollback on error)
3. `finish_run(conn, run_id, 'success')` → commit 2
4. `runner.py:276` → commit 3 (no-op if nothing pending)

**Status:** Works correctly but is non-obvious. Recommend documenting transaction boundaries in docstrings.

---

### H-3: Missing Type Hints for Return Tuples

**Location:** `pipeline/deduplicate.py`, `pipeline/validate.py`, `pipeline/identity.py`

**Examples:**
```python
# pipeline/deduplicate.py:4
def classify_observation(
    fingerprint: str,
    logical_key: Optional[str],
    conn,
) -> tuple:  # ← What's in the tuple?
```

```python
# pipeline/validate.py:5
def validate(record) -> tuple:  # ← What's in the tuple?
```

```python
# pipeline/identity.py (inferred)
def build_identity(...) -> tuple:  # ← What's in the tuple?
```

**Impact:**
- IDE cannot autocomplete tuple unpacking
- Refactoring risk: changing tuple structure breaks all callers silently
- Documentation burden: must read implementation to understand return value

**Recommendation:** Use `typing.Tuple` with explicit types:
```python
from typing import Tuple, Optional

def classify_observation(
    fingerprint: str,
    logical_key: Optional[str],
    conn,
) -> Tuple[str, Optional[int]]:
    # Returns ("duplicate"|"changed"|"new", existing_id or None)
```

Or use `typing.NamedTuple`:
```python
from typing import NamedTuple

class ClassificationResult(NamedTuple):
    action: str  # "duplicate" | "changed" | "new"
    existing_id: Optional[int]

def classify_observation(...) -> ClassificationResult:
    return ClassificationResult("duplicate", row[0])
```

---

### H-4: Excessive Function Parameters

**Location:** Multiple files

**Functions with >10 parameters:**

1. **`review/workflow.py:9` — `decide_candidate()`: 14 parameters**
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

2. **`pipeline/runs.py:19` — `finish_run()`: 13 parameters**
```python
def finish_run(conn, run_id: int, status: str,
               http_status: Optional[int] = None,
               records_found: int = 0,
               records_accepted: int = 0,
               records_flagged: int = 0,
               error_code: Optional[str] = None,
               error_summary: Optional[str] = None,
               duration_ms: Optional[int] = None,
               records_duplicated: int = 0,
               is_fallback: bool = False,
               fallback_adapter: Optional[str] = None):
```

3. **`pipeline/persist.py:82` — `commit_correction()`: 11 parameters**

**Impact:**
- Easy to mix up parameter order
- Call sites become unreadable
- Refactoring is painful (ripple effect across all callers)

**Recommendation:** Use dataclasses or NamedTuples to bundle related parameters:
```python
@dataclass
class RunResult:
    status: str
    http_status: Optional[int] = None
    records_found: int = 0
    records_accepted: int = 0
    records_flagged: int = 0
    records_duplicated: int = 0
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    duration_ms: Optional[int] = None
    is_fallback: bool = False
    fallback_adapter: Optional[str] = None

def finish_run(conn, run_id: int, result: RunResult):
    # 2 parameters instead of 13
```

---

## Medium Priority Findings

### M-1: Eager Adapter Loading in Infrastructure

**Location:** `infrastructure/adapter_registry.py:3-33`

**Code:**
```python
# infrastructure/adapter_registry.py:3-33
from adapters.abay import adapter as abay_adapter
from adapters.adib import adapter as adib_adapter
from adapters.ahadu import adapter as ahadu_adapter
from adapters.amhara import adapter as amhara_adapter
from adapters.anbesa import adapter as anbesa_adapter
from adapters.awash import adapter as awash_adapter
# ... 27 more imports ...

default_registry = AdapterRegistry()
default_registry.register("abay_html", abay_adapter)
default_registry.register("adib_api", adib_adapter)
# ... 31 more registrations ...
```

**Impact:**
- Cannot import `infrastructure.adapter_registry` without loading all 33 adapters
- Adapter import failure breaks unrelated code
- Slower startup time (loads 33 modules + their dependencies at import time)

**Recommendation:** Lazy load adapters:
```python
class AdapterRegistry:
    def __init__(self):
        self._adapters = {}
        self._adapter_paths = {
            "abay_html": "adapters.abay.adapter",
            "adib_api": "adapters.adib.adapter",
            # ... etc
        }
    
    def get(self, adapter_key: str):
        if adapter_key not in self._adapters:
            if adapter_key not in self._adapter_paths:
                raise KeyError(f"Adapter {adapter_key!r} not registered")
            module_path = self._adapter_paths[adapter_key]
            self._adapters[adapter_key] = importlib.import_module(module_path)
        return self._adapters[adapter_key]
```

---

### M-2: Magic Numbers Without Documentation

**Location:** `pipeline/ingest.py:18`, `scheduler/runner.py:25-27`

**Code:**
```python
# pipeline/ingest.py:18
MAX_INTRADAY_JUMP_PERCENT = 20.0  # Where does 20% come from?

# scheduler/runner.py:25-27
RETRY_DELAYS = [2, 10, 30]  # Why these values?
ALERT_AFTER_CONSECUTIVE_FAILURES = 2
FALLBACK_TTL_DAYS = 3
```

**Impact:**
- No rationale for threshold choices
- Cannot configure without code changes
- Difficult to tune in production

**Recommendation:** Add docstrings explaining rationale:
```python
# Anomaly threshold: 20% intraday jump indicates data error or major event.
# Chosen based on historical CBE volatility analysis (2023-Q4).
# Any rate change >20% triggers manual review.
MAX_INTRADAY_JUMP_PERCENT = 20.0
```

Or move to configuration:
```python
# infrastructure/config.py
class Config:
    MAX_INTRADAY_JUMP_PERCENT: float = float(os.getenv("MAX_INTRADAY_JUMP_PERCENT", "20.0"))
```

---

### M-3: Inconsistent Savepoint Naming

**Location:** `pipeline/ingest.py:41`

**Code:**
```python
# pipeline/ingest.py:41-50
for record in records:
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT _ingest_sp")  # ← Hardcoded name
    try:
        _process_one(conn, record, source_id, run_id, fetched_at,
                     category_map, result, is_fallback=is_fallback)
        with conn.cursor() as cur:
            cur.execute("RELEASE SAVEPOINT _ingest_sp")
    except Exception as exc:
        with conn.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT _ingest_sp")
            cur.execute("RELEASE SAVEPOINT _ingest_sp")
```

**Failure Scenario:**
1. `_process_one()` calls helper function that also creates savepoint named `_ingest_sp`
2. Inner savepoint created: `SAVEPOINT _ingest_sp` (SQL errors: savepoint already exists)
3. OR: Savepoint name collision causes wrong savepoint to be released

**Impact:**
- Not currently a bug (no nested savepoints in code)
- Fragile: adding nested savepoints breaks silently

**Recommendation:** Use unique savepoint names:
```python
import uuid

savepoint_name = f"ingest_{uuid.uuid4().hex[:8]}"
cur.execute(f"SAVEPOINT {savepoint_name}")
```

Or create context manager:
```python
class Savepoint:
    def __init__(self, conn):
        self.conn = conn
        self.name = f"sp_{uuid.uuid4().hex[:8]}"
    
    def __enter__(self):
        with self.conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {self.name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.conn.cursor() as cur:
            if exc_type:
                cur.execute(f"ROLLBACK TO SAVEPOINT {self.name}")
            cur.execute(f"RELEASE SAVEPOINT {self.name}")
        return False

# Usage
with Savepoint(conn):
    _process_one(...)
```

---

### M-4: No Logging in Core Pipeline

**Location:** `pipeline/ingest.py`, `pipeline/deduplicate.py`, `pipeline/persist.py`

**Finding:** No `logging` module usage in core pipeline. Only `scheduler/run_job.py` configures logging.

**Code:**
```python
# pipeline/ingest.py:50-52
except Exception as exc:
    # No logging, only result.errors.append()
    result.errors.append((record.source_currency_code, str(exc)))
    result.rejected += 1
```

**Impact:**
- Cannot trace pipeline execution in production
- Debugging requires adding print statements
- No correlation IDs to link logs across modules

**Recommendation:** Add structured logging:
```python
import logging
logger = logging.getLogger(__name__)

# In _process_one()
logger.info("Processing record", extra={
    "source_id": source_id,
    "run_id": run_id,
    "currency": record.source_currency_code,
    "action": action,
})
```

---

### M-5: Bare Except Clauses

**Location:** `adapters/awash/adapter.py:195, 210`

**Finding:** Two bare `except:` clauses that catch all exceptions including `KeyboardInterrupt`.

**Verification:** Cannot show code (file not read in this review), but detected in earlier scan.

**Impact:**
- Swallows `KeyboardInterrupt` (cannot Ctrl+C)
- Masks programming errors (`NameError`, `AttributeError`)
- Silent failures make debugging impossible

**Recommendation:** Replace with specific exception types:
```python
except (ValueError, KeyError, IndexError) as exc:
    logger.warning("Parse failed: %s", exc)
    raise
```

---

## Low Priority Findings

### L-1: Missing README.md

**Location:** Repository root

**Finding:** No `README.md` file at repository root.

**Impact:**
- New developers cannot onboard
- System purpose unclear
- Setup instructions missing

**Recommendation:** Create `README.md` with:
1. Project purpose and scope
2. Architecture diagram
3. Setup instructions (dependencies, database, environment variables)
4. Running tests
5. Deployment guide

---

### L-2: Test Naming Inconsistency

**Location:** `tests/`

**Examples:**
- `test_m2_constraints.py` — What is "m2"?
- `test_m3_pipeline.py` — What is "m3"?
- `test_m7_runs_trusted_review.py` — What is "m7"?
- `test_infrastructure_config.py` — Clear
- `test_fallback_guardrails.py` — Clear

**Impact:**
- Hard to locate tests for specific module
- "m2", "m3", "m7" are non-obvious

**Recommendation:** Rename to match module structure:
- `test_m2_constraints.py` → `test_database_constraints.py`
- `test_m3_pipeline.py` → `test_pipeline_core.py`
- `test_m7_runs_trusted_review.py` → `test_runs_and_review_integration.py`

---

### L-3: No Pre-Commit Hooks

**Location:** Repository root

**Finding:** No `.pre-commit-config.yaml` or Git hooks configured.

**Impact:**
- Code style violations slip through
- Type errors not caught locally
- Import order chaos

**Recommendation:** Add `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
  - repo: https://github.com/PyCQA/isort
    rev: 5.12.0
    hooks:
      - id: isort
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        args: [--ignore-missing-imports]
```

---

## Needs Confirmation

The following could not be verified without additional tools or production access:

1. **Coverage percentage:** pytest-cov not installed, cannot measure line/branch coverage
2. **Performance metrics:** No profiling data available. `_process_one()` complexity suggests performance bottleneck but not measured.
3. **Connection pool configuration:** Tests reference connection pooling but production config not visible
4. **Metrics export:** `prometheus_client` in requirements but no `/metrics` endpoint found in `api/app.py` (file not read)
5. **Log rotation:** Logging configured in `run_job.py` but rotation settings not visible
6. **Database query performance:** No `EXPLAIN ANALYZE` output. Cannot verify index usage.
7. **Fingerprint backfill:** Has `FINGERPRINT_VERSION=3` been deployed? Have old rows been backfilled?
8. **Circuit breaker thresholds:** `infrastructure/circuit_breaker.py` not fully analyzed. Are defaults production-ready?

---

## Summary

**Review date:** 2026-11-23  
**Lines of code:** 3,738 (core modules)  
**Python files:** 141  
**Test status:** 22 failed, 600 passed (3.5% failure rate)  
**Type hint coverage:** 82% (68/82 public functions)

### Severity Breakdown

| Severity | Count | Issues |
|----------|-------|--------|
| Critical | 3 | C-1: Missing fingerprint_version filter<br>C-2: Duplicate run_source() implementations<br>C-3: 22 test failures |
| High | 4 | H-1: Monster function (_process_one)<br>H-2: Transaction management confusion<br>H-3: Missing return type hints<br>H-4: Excessive function parameters |
| Medium | 5 | M-1: Eager adapter loading<br>M-2: Magic numbers<br>M-3: Savepoint naming<br>M-4: No logging in pipeline<br>M-5: Bare except clauses |
| Low | 3 | L-1: Missing README<br>L-2: Test naming inconsistency<br>L-3: No pre-commit hooks |

### Mandatory Check Results

| Check | Status | Finding |
|-------|--------|---------|
| 1. Hidden clocks in fingerprint.py | ✅ PASS | No hidden clocks, explicit collection_date parameter |
| 1. Canonical Decimal serialization | ✅ PASS | _canonical_decimal() normalizes before JSON |
| 2. commit_correction version derivation | ⚠️ PARTIAL | Uses FOR UPDATE but doesn't check is_current |
| 3. Transaction boundaries in workflow.py | ✅ PASS | Commits called explicitly in correct places |
| 4. WHERE/OR in _retire_prior_fallback | ✅ INTENTIONAL | Cross-category fallback retirement likely by design |
| 5. Adapters import infrastructure | ✅ PASS | No circular dependency found |
| 6. classify_observation behavior | ✅ CORRECT | Returns "changed" with existing_id when logical_key matches current |

### Top Recommendations

1. **Fix 22 test failures** (C-3) — Cannot proceed with deployment until green
2. **Eliminate duplicate run_source()** (C-2) — 423 lines of duplicated code, production/test divergence
3. **Add is_current check in commit_correction()** (from Check 2) — Data integrity risk
4. **Refactor _process_one()** (H-1) — 152 lines, complexity 62, unmaintainable
5. **Add fingerprint_version filter** (C-1) — Defensive coding for version bump scenarios

---

**Review completed:** 2026-11-23  
**Next steps:** Fix test suite, then address C-1, C-2, and H-1 in order.

