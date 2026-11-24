# Scheduler Runner Refactoring Plan - CORRECTED
## Based on Actual Behavior from Characterization Tests

**Last Updated:** After characterization test fixes and coverage measurement
**Coverage:** 78% (322 stmts, 59 missed, 108 branches, 20 partial)
**Tests:** 644 passing (635 original + 9 characterization)

---

## Executive Summary

This document provides the **corrected** refactoring plan for `scheduler/runner.py`, incorporating findings from characterization tests that revealed:
- 2 confirmed HIGH priority bugs (double-status, dry-run orphans)
- Actual transaction ownership (not what was assumed)
- Real return dict structures for all 8 exit paths
- Dataclass boundaries requiring conversion

---

## Section 1: Actual Commit/Rollback Ownership (CORRECTED)

### Transaction Points in Current Code

| Line | Operation | Owner | Commits Internally? | Notes from Tests |
|------|-----------|-------|---------------------|------------------|
| 101 | `recover_stuck_run(conn, source_id)` | `pipeline.runs` | YES | Side effect, happens before start_run |
| 102 | `start_run(conn, source_id)` | `pipeline.runs` | YES | **BUG: Commits even in dry_run mode** |
| 108 | `conn.rollback()` | `run_source` | N/A | UniqueViolation handler (concurrent run) |
| 184 | `finish_run(conn, run_id, "failed", ...)` | `pipeline.runs` | NO | Stale/zero path, first finish call |
| 186 | `_increment_failure_counter(...)` | `run_source` via helper | NO | Updates rate_source.consecutive_failures |
| 188 | `_write_alert(...)` | `run_source` via helper | NO | Inserts into alert table |
| 189 | `conn.commit()` | `run_source` | YES | **Commits failed run + alert** |
| 191 | `_try_af_fallback(...)` | Helper function | YES (internally) | See fallback table below |
| 198 | `result = ingest(...)` | `pipeline.ingest` | NO | Uses savepoints internally |
| 202 | `finish_run(conn, run_id, "success", ...)` | `pipeline.runs` | NO | **SECOND finish_run for stale path!** |
| 204 | `repo.update_last_success(source_id)` | Repository | NO | Updates rate_source.last_success_at |
| 205 | `_reset_failure_counter(conn, source_id)` | Helper | NO | Resets consecutive_failures to 0 |
| 206 | `conn.commit()` | `run_source` | YES | **Commits stale-but-retained success** |
| 217 | `repo.update_schema_fingerprint(...)` | Repository | NO | Updates rate_source.schema_fingerprint |
| 220 | `result = ingest(...)` | `pipeline.ingest` | NO | Uses savepoints internally |
| 222 | `_store_raw_capture(...)` | Helper | NO | Stores suspicious data |
| 228 | `conn.rollback()` | `run_source` | YES | **Dry-run rollback (but start_run already committed!)** |
| 243 | `finish_run(conn, run_id, run_status, ...)` | `pipeline.runs` | NO | Normal success path |
| 248 | `_expire_stale_fallback_current(...)` | Helper | NO | Side effect, no return value |
| 251 | `conn.commit()` | `run_source` | YES | **Commits normal success** |
| 276-279 | `_store_raw_capture(...)` in except | Helper | NO | **BUG: Silent failure (bare except: pass)** |
| 282 | `finish_run(conn, run_id, "failed", ...)` | `pipeline.runs` | NO | Exception handler path |
| 286 | `_write_alert(...)` | Helper | NO | Conditional alert |
| 287 | `conn.commit()` | `run_source` | YES | **Commits exception failure** |
| 289 | `conn.rollback()` | `run_source` (except) | YES | If finish_run itself fails |
| 291 | `_try_af_fallback(...)` | Helper | YES (internally) | Last-ditch fallback attempt |

### Fallback Function Transaction Ownership

`_try_af_fallback()` manages its own transaction (lines 490-557):

| Line | Operation | Commits? | Notes |
|------|-----------|----------|-------|
| 497 | `start_run(conn, fallback_source_id)` | YES | Commits new run record |
| 532 | `finish_run(conn, fb_run_id, status, ...)` | NO | Called before commit |
| 533 | `conn.commit()` | YES | **Fallback success commit** |
| 547 | `finish_run(conn, fb_run_id, "failed", ...)` | NO | Fallback failed |
| 550 | `conn.commit()` | YES | **Fallback failure commit** |

**KEY FINDINGS:**
1. **`start_run()` ALWAYS commits** - This causes the dry-run bug (orphaned runs)
2. **Stale path has TWO finish_run() calls and TWO commits** - Lines 184→189 then 202→206
3. **`_try_af_fallback()` manages own transaction** - Parent doesn't need to commit its results
4. **Exception path has nested try/except** - Inner commit at 287, outer rollback at 289

---

## Section 2: All Return Dict Structures (CORRECTED)

### Exit Path 1: Source Not Found (Line 80)
```python
{
    "source_id": int,
    "status": "error",
    "detail": "source not found"
}
```
**Transaction:** None (early return)

### Exit Path 2: Circuit Breaker Open - No Fallback (Line 89)
```python
{
    "source_id": int,
    "status": "skipped",
    "detail": "circuit breaker open",
    "adapter_key": str
}
```
**Transaction:** None

### Exit Path 3: Circuit Breaker Open - Fallback Success (Line 87-88)
```python
{
    "source_id": int,
    "status": "success",  # or "partial_success"
    "accepted": int,
    "flagged": int,
    "rejected": int,
    "duplicates": int,
    "candidates": int,
    "is_fallback": bool,
    "fallback_adapter": str
}
```
**Transaction:** Committed by `_try_af_fallback()` internally

### Exit Path 4: Concurrent Run (Line 109)
```python
{
    "source_id": int,
    "status": "skipped",
    "detail": "run already in progress"
}
```
**Transaction:** Rollback at line 108 (after UniqueViolation)
**Test:** `test_concurrent_run_returns_skipped_status()` ✅

### Exit Path 5: Zero Records - No Fallback (Line 229)
```python
{
    "source_id": int,
    "status": "failed",
    "error_code": "zero_records_extracted",
    "detail": "Primary returned 0 records; fallback invoked"
}
```
**Transaction:** Commit at line 189 (failed run + alert if threshold reached)
**Test:** `test_zero_records_does_not_ingest_when_no_fallback()` ✅

### Exit Path 6: Stale Records - Retained (Line 207-213)
```python
{
    "source_id": int,
    "status": "success",
    "accepted": int,
    "flagged": int,
    "rejected": int,
    "duplicates": int
}
```
**Note:** NO `candidates` or `schema_changed` keys in this path
**Transaction:** TWO commits - line 189 (failed), line 206 (success)
**Test:** `test_stale_records_retained_as_standing_rate()` ✅
**BUG:** Double status (failed→success), double commit

### Exit Path 7: Dry-Run (Line 229-240)
```python
{
    "source_id": int,
    "status": "dry_run",
    "records_found": int,
    "would_accept": int,
    "would_reject": int,
    "would_flag": int,
    "would_duplicate": int,
    "schema_changed": bool,
    "duration_ms": int
}
```
**Transaction:** Rollback at line 228 (observations not persisted)
**Test:** `test_dry_run_rolls_back_all_changes()` ✅
**BUG:** collection_run record IS created (start_run committed at line 102)

### Exit Path 8: Normal Success (Line 252-260)
```python
{
    "source_id": int,
    "status": "success",  # or "partial_success"
    "accepted": int,
    "flagged": int,
    "rejected": int,
    "duplicates": int,
    "candidates": int,
    "schema_changed": bool
}
```
**Transaction:** Commit at line 251
**Test:** Covered by multiple tests ✅

### Exit Path 9: Exception - No Fallback (Line 294-299)
```python
{
    "source_id": int,
    "status": "failed",
    "error_code": str,
    "detail": str  # error_summary
}
```
**Transaction:** Commit at line 287 (or rollback at 289 if finish_run fails)
**Test:** `test_parse_error_attempts_raw_capture_even_if_it_fails()` ✅

### Exit Path 10: Exception - Fallback Success (Line 291-293)
```python
{
    "source_id": int,
    "status": "success",  # or "partial_success"
    "accepted": int,
    "flagged": int,
    "rejected": int,
    "duplicates": int,
    "candidates": int,
    "is_fallback": bool,
    "fallback_adapter": str
}
```
**Transaction:** Committed by `_try_af_fallback()` internally

---

## Section 3: Orchestrator Logic Statement-by-Statement Comparison

### Current run_source() Flow (Lines 76-305)

```python
# PHASE 0: Pre-flight checks (NO transaction yet)
def run_source(self, conn, source_id: int) -> dict:
    repo = RateSourceRepository(conn)
    source = repo.get_by_id(source_id)
    if source is None:
        return EXIT_PATH_1  # source not found
    
    # Circuit breaker check
    if not self.circuit_breaker.should_attempt(adapter_key):
        af_res = _try_af_fallback(...)  # Commits internally if succeeds
        if af_res is not None:
            return EXIT_PATH_3  # fallback success
        return EXIT_PATH_2  # circuit breaker open, no fallback
    
    # SIDE EFFECT: Recover stuck runs (commits internally)
    recover_stuck_run(conn, source_id)
    
    # PHASE 1: Start run (COMMITS IMMEDIATELY - causes dry-run bug)
    try:
        run_id = start_run(conn, source_id)  # <-- COMMITS HERE
    except UniqueViolation:
        conn.rollback()
        return EXIT_PATH_4  # concurrent run
    
    t0 = time.monotonic()
    raw_content = None
    http_status = None
    
    # PHASE 2: Main try block (fetch → parse → decide → ingest)
    try:
        # 2.1: Fetch (20-50 lines of adapter loading + HTTP logic)
        adapter = self.adapter_registry.get(adapter_key)
        # ... complex fetch logic (browser vs fetch_raw vs http_client) ...
        raw_content, http_status = <fetch result>
        
        # 2.2: Schema check (side effect: stores raw_capture if changed)
        schema_changed = _check_schema(conn, run_id, source, adapter, raw_content, repo)
        
        # 2.3: Parse
        category = source.get("default_category") or "UNKNOWN"
        records = _parse(adapter, raw_content, category)
        
        # DECISION POINT: Zero or stale?
        all_stale = len(records) > 0 and all(
            r.effective_date and (date.today() - r.effective_date).days > 3 
            for r in records
        )
        
        if len(records) == 0 or all_stale:
            # ZERO/STALE PATH (lines 169-227)
            err_code = "zero_records_extracted" if len(records) == 0 else "stale_feed"
            err_summary = ...
            
            # First finish_run as FAILED
            finish_run(conn, run_id, "failed", ...)
            needs_alert = _increment_failure_counter(conn, source_id, err_code)
            if needs_alert:
                _write_alert(conn, source_id, err_code, err_summary)
            conn.commit()  # COMMIT #1
            
            # Try fallback
            af_res = _try_af_fallback(...)  # Commits internally
            if af_res is not None:
                return af_res  # Fallback succeeded, return its result
            
            # If stale (not zero), INGEST ANYWAY
            if all_stale and len(records) > 0:
                fetched_at = datetime.now(timezone.utc)
                result = ingest(conn, records, source_id, run_id, ...)
                
                # Second finish_run as SUCCESS (BUG!)
                finish_run(conn, run_id, "success", ...)
                repo.update_last_success(source_id)
                _reset_failure_counter(conn, source_id)
                conn.commit()  # COMMIT #2
                return EXIT_PATH_6  # stale retained
            
            return EXIT_PATH_5  # zero records, no fallback
        
        # NORMAL PATH (lines 215-260)
        if schema_changed:
            new_fp = adapter.schema_fingerprint(raw_content)
            repo.update_schema_fingerprint(source_id, new_fp)
        
        fetched_at = datetime.now(timezone.utc)
        result = ingest(conn, records, source_id, run_id, ...)
        
        if result.suspicious:
            _store_raw_capture(conn, run_id, "suspicious_data", raw_content)
        
        duration_ms = int((time.monotonic() - t0) * 1000)
        run_status = _run_status(result)
        
        # DRY-RUN CHECK (after ingest!)
        if self.dry_run:
            conn.rollback()  # Rolls back ingest, BUT start_run already committed (BUG!)
            return EXIT_PATH_7  # dry_run
        
        # Finish normally
        finish_run(conn, run_id, run_status, ...)
        
        if run_status in ("success", "partial_success"):
            repo.update_last_success(source_id)
            _reset_failure_counter(conn, source_id)
            self.circuit_breaker.record_success(adapter_key)
            _expire_stale_fallback_current(conn, source_id)  # SIDE EFFECT
        
        conn.commit()  # COMMIT #3 (normal success)
        return EXIT_PATH_8  # success
    
    # PHASE 3: Exception handler
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_code, error_summary = self.error_classifier.classify(exc)
        
        self.circuit_breaker.record_failure(adapter_key)
        
        # Try to store raw (silent failure - BUG!)
        if raw_content and error_code in ("parse_failure", "schema_change"):
            try:
                _store_raw_capture(conn, run_id, error_code, raw_content)
            except Exception:
                pass  # <-- SILENT FAILURE
        
        # Try to finish run + alert
        try:
            finish_run(conn, run_id, "failed", ...)
            needs_alert = _increment_failure_counter(conn, source_id, error_code)
            if needs_alert:
                _write_alert(conn, source_id, error_code, error_summary)
            conn.commit()  # COMMIT #4 (exception path)
        except Exception:
            conn.rollback()  # If finish_run itself fails
        
        # Last-ditch fallback attempt
        af_result = _try_af_fallback(...)  # Commits internally
        if af_result:
            return EXIT_PATH_10  # fallback success
        
        return EXIT_PATH_9  # failed, no fallback
```

### Proposed Orchestrator (15 lines target)

```python
def run_source(self, conn, source_id: int) -> dict:
    """Orchestrate collection run. All seams are pre-extracted."""
    # Phase 0: Pre-flight
    source = parse_and_validate_source(conn, source_id, self.circuit_breaker)
    if source.should_skip:
        return source.skip_result  # Includes fallback if applicable
    
    # Phase 1: Fetch → Parse → Decide
    collection_input = fetch_and_parse(conn, source, self.adapter_registry, self.config)
    decision = decide_handling(collection_input)
    
    # Phase 2: Record outcome
    result = record_collection_outcome(
        conn, decision, collection_input, 
        dry_run=self.dry_run, circuit_breaker=self.circuit_breaker
    )
    return result.to_dict()
```

**Deviation from Current:**
- Current: 230 lines of mixed concerns
- Proposed: 15 lines calling extracted functions
- Current: 4 different commit points scattered
- Proposed: All transaction ownership in `record_collection_outcome()`
- Current: Side effects invisible
- Proposed: Side effects in return value or explicit

**Statement-by-Statement Match:** The proposed orchestrator calls extracted functions that contain the EXACT logic from current code. No behavior changes. The extraction is purely organizational.

---

## Section 4: Dataclass-to-Dict Conversion Boundaries

### Input Boundary: source dict → SourceConfig

**Current:** `source` is a dict from `repo.get_by_id()`
```python
source = {
    "id": int,
    "bank_id": int,
    "adapter_key": str,
    "source_url": str,
    "ssl_verify": bool,
    "default_category": str | None,
    "schema_fingerprint": str | None,
    "verification_status": str,
    # ... other columns
}
```

**Proposed:** Convert to frozen dataclass at module boundary
```python
@dataclass(frozen=True)
class SourceConfig:
    source_id: int
    adapter_key: str
    source_url: str
    ssl_verify: bool
    default_category: str
    schema_fingerprint: str | None
    
    @classmethod
    def from_db_row(cls, row: dict) -> "SourceConfig":
        return cls(
            source_id=row["id"],
            adapter_key=row["adapter_key"],
            source_url=row["source_url"],
            ssl_verify=row["ssl_verify"],
            default_category=row.get("default_category") or "UNKNOWN",
            schema_fingerprint=row.get("schema_fingerprint"),
        )
```

**Test Equality:**
```python
# Original
source_dict = repo.get_by_id(source_id)
result = run_source(conn, source_id)

# After extraction
source_dict = repo.get_by_id(source_id)
source_config = SourceConfig.from_db_row(source_dict)
# Assert key-for-key equality:
assert source_config.source_id == source_dict["id"]
assert source_config.adapter_key == source_dict["adapter_key"]
# ... etc for all fields

result = run_source_refactored(conn, source_config)
```

### Output Boundary: CollectionResult → dict

**Current:** Functions return dicts with varying keys (10 different shapes)

**Proposed:** Frozen dataclass with explicit conversions
```python
@dataclass(frozen=True)
class CollectionResult:
    source_id: int
    status: str  # "success", "failed", "skipped", "dry_run", "error"
    
    # Metrics (Optional - only on success/dry_run)
    accepted: int | None = None
    flagged: int | None = None
    rejected: int | None = None
    duplicates: int | None = None
    candidates: int | None = None
    
    # Metadata (Optional)
    error_code: str | None = None
    detail: str | None = None
    adapter_key: str | None = None
    schema_changed: bool | None = None
    duration_ms: int | None = None
    
    # Dry-run specific
    would_accept: int | None = None
    would_reject: int | None = None
    would_flag: int | None = None
    would_duplicate: int | None = None
    records_found: int | None = None
    
    # Fallback
    is_fallback: bool = False
    fallback_adapter: str | None = None
    
    def to_dict(self) -> dict:
        """Convert to dict, excluding None values."""
        return {
            k: v for k, v in asdict(self).items() 
            if v is not None
        }
```

**Test Equality:** For each exit path, assert key-for-key equality:
```python
# Example: Concurrent run path
original_result = {
    "source_id": 123,
    "status": "skipped",
    "detail": "run already in progress"
}

refactored_result = CollectionResult(
    source_id=123,
    status="skipped",
    detail="run already in progress"
).to_dict()

assert original_result == refactored_result  # Key-for-key equality
assert set(original_result.keys()) == set(refactored_result.keys())
for key in original_result:
    assert original_result[key] == refactored_result[key]
```

---

## Section 5: Extraction Module Structure (5 Modules)

### Module 1: scheduler/extraction/input_parser.py
**Responsibility:** Pre-flight checks, source validation, circuit breaker logic
**Functions:**
- `parse_and_validate_source(conn, source_id, circuit_breaker) -> SourceConfig | SkipResult`
- `check_circuit_breaker(adapter_key, circuit_breaker) -> bool`
- `recover_stuck_run_if_needed(conn, source_id) -> None`  # Side effect wrapper

**Inputs:** conn, source_id, circuit_breaker
**Outputs:** SourceConfig dataclass OR SkipResult with early-return dict
**Transaction:** Read-only except recover_stuck_run (commits internally)
**Lines Extracted:** 76-101
**Tests:** test_concurrent_run, existing tests for circuit breaker

### Module 2: scheduler/extraction/fetcher.py
**Responsibility:** Adapter loading, HTTP fetching, schema checking
**Functions:**
- `fetch_and_parse(conn, source, adapter_registry, config) -> CollectionInput`
- `_load_and_configure_adapter(source, adapter_registry) -> adapter`
- `_fetch_content(adapter, source, config) -> (raw_content, http_status)`
- `_check_and_store_schema_change(conn, run_id, source, adapter, raw_content) -> bool`

**Inputs:** SourceConfig, adapter_registry, config
**Outputs:** CollectionInput dataclass containing:
  - `records: list[AdapterRecord]`
  - `raw_content: str`
  - `http_status: int`
  - `schema_changed: bool`
  - `duration_ms: int`
  - `adapter_key: str`

**Transaction:** Read-only + schema_changed raw_capture (no commit)
**Lines Extracted:** 113-166
**Tests:** test_schema_change_stores_raw_capture, existing adapter tests

### Module 3: scheduler/extraction/decision.py
**Responsibility:** Decide what to do with parsed records (zero/stale/normal)
**Functions:**
- `decide_handling(collection_input: CollectionInput) -> HandlingDecision`
- `_classify_records(records) -> RecordClassification`  # zero/stale/normal

**Inputs:** CollectionInput dataclass
**Outputs:** HandlingDecision dataclass containing:
  - `classification: Literal["zero", "stale", "normal"]`
  - `should_ingest: bool`
  - `error_code: str | None`
  - `error_summary: str | None`
  - `should_try_fallback: bool`

**Transaction:** None (pure logic)
**Lines Extracted:** 167-171 (decision logic only, not execution)
**Tests:** test_stale_records, test_zero_records

### Module 4: scheduler/extraction/recorder.py
**Responsibility:** Execute decided handling, manage transactions, record outcomes
**Functions:**
- `record_collection_outcome(conn, decision, input, dry_run, circuit_breaker) -> CollectionResult`
- `_handle_zero_or_stale_path(conn, decision, input) -> CollectionResult | None`
- `_handle_normal_path(conn, input, dry_run) -> CollectionResult`
- `_handle_exception_path(conn, exc, input, circuit_breaker) -> CollectionResult`
- `_try_fallback_if_applicable(conn, source_id, adapter_key, user_agent) -> CollectionResult | None`

**Inputs:** HandlingDecision, CollectionInput, dry_run flag
**Outputs:** CollectionResult dataclass
**Transaction:** OWNS ALL COMMITS - lines 189, 206, 251, 287
**Lines Extracted:** 172-305 (execution paths)
**Tests:** ALL characterization tests (this is where transaction ownership matters)

**Key Transaction Responsibilities:**
- Zero/stale path: Commit at 189, then possibly 206 if stale retained (BUG preserved)
- Normal path: Commit at 251
- Dry-run: Rollback at 228 (but start_run already committed - BUG preserved)
- Exception: Commit at 287 or rollback at 289

### Module 5: scheduler/extraction/orchestrator.py
**Responsibility:** Top-level coordination only (15 lines)
**Functions:**
- `run_source_orchestrated(conn, source_id, config, registries, circuit_breaker, dry_run) -> dict`

**Inputs:** All dependencies explicitly passed
**Outputs:** dict (via CollectionResult.to_dict())
**Transaction:** None (delegates to recorder)
**Lines Extracted:** None (new glue code)
**Tests:** ALL existing tests must pass unchanged

---

## Section 6: Extraction Order & Commit Strategy

### Phase 1: Extract Parser (Lowest Risk)
**Commit:** "Extract input parser: source validation + circuit breaker logic"
**Files Changed:**
- NEW: `scheduler/extraction/input_parser.py`
- MODIFIED: `scheduler/runner.py` (lines 76-101 → call parser)
**Tests:** Run full suite (should be 644 passing)
**Risk:** LOW - No transaction logic, mostly reads

### Phase 2: Extract Fetcher
**Commit:** "Extract fetcher: adapter loading + HTTP + schema check"
**Files Changed:**
- NEW: `scheduler/extraction/fetcher.py`
- MODIFIED: `scheduler/runner.py` (lines 113-166 → call fetcher)
**Tests:** Run full suite + coverage check
**Risk:** LOW - schema_changed raw_capture is side effect but doesn't commit

### Phase 3: Extract Decision
**Commit:** "Extract decision logic: classify records as zero/stale/normal"
**Files Changed:**
- NEW: `scheduler/extraction/decision.py`
- MODIFIED: `scheduler/runner.py` (lines 167-171 → call decision)
**Tests:** Run full suite + test_stale + test_zero specifically
**Risk:** VERY LOW - Pure logic, no I/O

### Phase 4: Extract Recorder (HIGHEST RISK)
**Commit:** "Extract recorder: transaction ownership + outcome recording"
**Files Changed:**
- NEW: `scheduler/extraction/recorder.py`
- MODIFIED: `scheduler/runner.py` (lines 172-305 → call recorder)
**Tests:** Run FULL suite + ALL characterization tests
**Risk:** HIGH - Owns all commits, complex branching
**Verification Required:**
- All 644 tests pass
- Coverage remains ≥78%
- Characterization tests prove identical behavior
- Manual smoke test on dev environment

### Phase 5: Create Orchestrator
**Commit:** "Create thin orchestrator wrapper for run_source"
**Files Changed:**
- NEW: `scheduler/extraction/orchestrator.py`
- MODIFIED: `scheduler/runner.py` (keep old for backwards compat temporarily)
**Tests:** Run full suite with both old and new paths
**Risk:** LOW - Just glue code
**Strategy:** Run both implementations in parallel, assert results equal

### Phase 6: Deprecate Original (Future Work)
**Commit:** "Deprecate original run_source, migrate callers to orchestrator"
**Files Changed:** All callers of `Scheduler().run_source()`
**Tests:** Remove old implementation after migration
**Risk:** MEDIUM - Breaking change requires careful coordination

---

## Section 7: Line-by-Line Mapping (Corrected)

### Current run_source (Lines 76-305)

| Current Lines | Responsibility | Extracted To | Module | Function |
|---------------|----------------|--------------|--------|----------|
| 76-80 | Load source from DB | input_parser | 1 | parse_and_validate_source |
| 81-83 | Validate source exists | input_parser | 1 | parse_and_validate_source |
| 84-96 | Circuit breaker check + fallback | input_parser | 1 | check_circuit_breaker |
| 97 | Side effect: recover stuck run | input_parser | 1 | recover_stuck_run_if_needed |
| 98-109 | Start run + concurrent check | recorder | 4 | (stays in recorder - transaction boundary) |
| 110-111 | Initialize timing + state | orchestrator | 5 | run_source_orchestrated |
| 113-123 | Load adapter from registry | fetcher | 2 | _load_and_configure_adapter |
| 124 | Get timeout config | fetcher | 2 | _fetch_content |
| 126-156 | Fetch logic (browser/raw/http) | fetcher | 2 | _fetch_content |
| 158 | Check schema changed | fetcher | 2 | _check_and_store_schema_change |
| 160-161 | Parse adapter output | fetcher | 2 | fetch_and_parse |
| 163-171 | Classify records (zero/stale/normal) | decision | 3 | decide_handling |
| 172-227 | Execute zero/stale path | recorder | 4 | _handle_zero_or_stale_path |
| 184 | finish_run("failed") - FIRST | recorder | 4 | _handle_zero_or_stale_path |
| 186-188 | Increment failure + alert | recorder | 4 | _handle_zero_or_stale_path |
| 189 | **COMMIT #1** | recorder | 4 | _handle_zero_or_stale_path |
| 191-193 | Try fallback | recorder | 4 | _try_fallback_if_applicable |
| 195-213 | Stale retained path | recorder | 4 | _handle_zero_or_stale_path |
| 198 | Ingest stale records | recorder | 4 | _handle_zero_or_stale_path |
| 202 | finish_run("success") - SECOND | recorder | 4 | _handle_zero_or_stale_path |
| 204-205 | Update success + reset counter | recorder | 4 | _handle_zero_or_stale_path |
| 206 | **COMMIT #2** (BUG: double commit) | recorder | 4 | _handle_zero_or_stale_path |
| 207-213 | Return stale success | recorder | 4 | _handle_zero_or_stale_path |
| 215-227 | Return zero failed | recorder | 4 | _handle_zero_or_stale_path |
| 215-217 | Update schema fingerprint | recorder | 4 | _handle_normal_path |
| 219-220 | Ingest normal records | recorder | 4 | _handle_normal_path |
| 222-223 | Store suspicious raw | recorder | 4 | _handle_normal_path |
| 225-226 | Calculate duration + status | recorder | 4 | _handle_normal_path |
| 228-240 | Dry-run branch | recorder | 4 | _handle_normal_path |
| 228 | **ROLLBACK** (BUG: start_run committed) | recorder | 4 | _handle_normal_path |
| 242-251 | Finish normal run | recorder | 4 | _handle_normal_path |
| 243 | finish_run(run_status) | recorder | 4 | _handle_normal_path |
| 245-249 | Update success + side effects | recorder | 4 | _handle_normal_path |
| 251 | **COMMIT #3** | recorder | 4 | _handle_normal_path |
| 252-260 | Return normal success | recorder | 4 | _handle_normal_path |
| 262-305 | Exception handler | recorder | 4 | _handle_exception_path |
| 263-264 | Classify error | recorder | 4 | _handle_exception_path |
| 266 | Record circuit breaker failure | recorder | 4 | _handle_exception_path |
| 268-271 | Store raw (silent fail - BUG) | recorder | 4 | _handle_exception_path |
| 273-287 | Finish failed + alert | recorder | 4 | _handle_exception_path |
| 287 | **COMMIT #4** | recorder | 4 | _handle_exception_path |
| 288-290 | Rollback if finish fails | recorder | 4 | _handle_exception_path |
| 292-294 | Try fallback | recorder | 4 | _try_fallback_if_applicable |
| 296-299 | Return exception failure | recorder | 4 | _handle_exception_path |

### Helper Functions (Lines 320-565)

| Current Lines | Function | Extracted To | Notes |
|---------------|----------|--------------|-------|
| 321-340 | _load_adapter | fetcher | Used in adapter loading |
| 342-351 | _classify_error | recorder | Used in exception handler |
| 353-379 | _fetch | fetcher | Used in HTTP client path |
| 381-385 | _fetch_browser | fetcher | Used in browser fetch path |
| 387-406 | _check_schema | fetcher | Used in schema detection |
| 411-424 | _parse | fetcher | Used in parsing step |
| 426-434 | _build_url | fetcher | Used in URL construction |
| 436-438 | _store_raw_capture | recorder | Used in raw storage |
| 440-445 | _run_status | recorder | Used in status determination |
| 447-454 | _reset_failure_counter | recorder | Used in success path |
| 456-476 | _increment_failure_counter | recorder | Used in failure tracking |
| 478-488 | _write_alert | recorder | Used in alert creation |
| 490-557 | _try_af_fallback | recorder | Fallback orchestration (commits internally) |
| 559-565 | _expire_stale_fallback_current | recorder | Side effect in success path |

---

## Section 8: Verification Strategy

### Pre-Extraction Checklist
- [x] All 644 tests passing
- [x] Coverage measured: 78% (322/59/108/20)
- [x] Characterization tests cover all critical paths
- [x] NOTES.md documents all known bugs
- [x] Return dict structures documented for all 10 exit paths
- [x] Transaction ownership mapped for all commit/rollback points

### During Each Extraction (Per-Commit)
1. **Code Changes:**
   - Create new module with extracted functions
   - Update original to call extracted functions
   - Run `ruff check` and `mypy` (zero new errors)

2. **Test Verification:**
   ```bash
   pytest tests/ -v
   # Must see: 644 passed
   
   pytest tests/test_characterization_runner.py -v
   # Must see: 9 passed
   
   pytest --cov=scheduler --cov-branch
   # Must see: ≥78% coverage for runner.py
   ```

3. **Behavior Verification:**
   - For recorder extraction specifically, add temporary logging:
   ```python
   # In OLD code
   logger.debug(f"OLD_PATH result: {result}")
   
   # In NEW code
   logger.debug(f"NEW_PATH result: {result}")
   
   # Then compare in tests
   ```

4. **Commit Message Template:**
   ```
   refactor(scheduler): Extract [module name] from runner.py
   
   Behavior-preserving extraction. Extracted lines [X-Y] to scheduler/extraction/[module].py.
   
   - Functions extracted: [list]
   - Tests: 644 passing (unchanged)
   - Coverage: [X]% (unchanged or improved)
   - Transaction ownership: [description if applicable]
   
   Part of scheduler refactoring plan. See docs/runner-refactoring-plan-corrected.md
   ```

### Post-Extraction Verification
- [ ] All 644 tests passing
- [ ] Coverage ≥78% (preferably improved)
- [ ] No new linter/type errors
- [ ] Manual smoke test on dev:
  - Successful run
  - Failed run with fallback
  - Dry-run mode
  - Concurrent run rejection
  - Alert generation after 3 failures
- [ ] Update docs/runner-refactoring-plan-corrected.md with actual results

---

## Section 9: Known Bugs to Preserve (Do NOT Fix During Refactoring)

### Bug #1: Double Status in Stale Path (Lines 184→206)
**Preserve:** Keep two finish_run() calls and two commits
**Why:** Characterization test `test_stale_records_retained_as_standing_rate()` pins this behavior
**Fix Later:** After refactoring, can safely fix in recorder module with new test

### Bug #2: Dry-Run Orphaned Runs (Lines 102→228)
**Preserve:** Keep start_run() before dry_run check
**Why:** Characterization test `test_dry_run_rolls_back_all_changes()` documents this
**Fix Later:** Move dry_run check before start_run() in separate PR

### Bug #3: Silent Raw Capture Failure (Lines 276-279)
**Preserve:** Keep bare `except: pass`
**Why:** Characterization test `test_parse_error_attempts_raw_capture_even_if_it_fails()` expects this
**Fix Later:** Add logging in separate PR

### Bug #4: Invisible Fallback Expiration (Line 267)
**Preserve:** Keep _expire_stale_fallback_current() as side effect with no return value
**Why:** Test documents current behavior
**Fix Later:** Add to CollectionResult in separate PR

**CRITICAL:** Fixing these bugs is OUT OF SCOPE for behavior-preserving refactoring. They must be fixed in separate PRs AFTER the extraction is complete.

---

## Section 10: Success Criteria

### Mandatory (Must Pass Before Merge)
- [ ] All 644 tests passing
- [ ] All 9 characterization tests passing
- [ ] Coverage ≥78% for scheduler/runner.py
- [ ] Zero new ruff/mypy errors
- [ ] All 4 extraction commits atomic (can rollback individually)
- [ ] Manual verification on dev environment

### Desirable (Nice to Have)
- [ ] Coverage improved (target: 80%+)
- [ ] Extracted modules have dedicated unit tests
- [ ] Documentation updated (architecture diagrams)
- [ ] Type hints 100% complete in extracted modules

### Blocked Until After Refactoring
- [ ] Fix Bug #1 (double status)
- [ ] Fix Bug #2 (dry-run orphans)
- [ ] Fix Bug #3 (silent failure)
- [ ] Fix Bug #4 (invisible side effect)
- [ ] Migrate callers to new orchestrator
- [ ] Deprecate original run_source()

---

## Appendix: Questions Resolved by Tests

### Q1: Who commits in stale/zero path?
**A:** `run_source` commits at line 189 (failed) and line 206 (success if stale retained). The stale path has DOUBLE commits (confirmed bug).

### Q2: What do real return dicts look like?
**A:** See Section 2. 10 different shapes documented. Key finding: `schema_changed` only in success/dry_run, not in failed paths. `candidates` only in normal success, not stale success.

### Q3: Does orchestrator logic match current run_source exactly?
**A:** Proposed orchestrator DELEGATES to extracted functions that contain exact current logic. The orchestrator is new glue code (15 lines) that calls: parser → fetcher → decision → recorder. See Section 3 for statement-by-statement comparison.

### Q4: Where do dataclass-to-dict conversions happen?
**A:** See Section 4. Input: `SourceConfig.from_db_row()` at module entry. Output: `CollectionResult.to_dict()` before return. All internal functions use dataclasses. Tests verify key-for-key equality at boundaries.

### Q5: What about the line-range table 563 vs 565 contradiction?
**A:** File is 565 lines total (confirmed by grep). The contradiction was in stale path (lines 193-227 in original plan). Corrected mapping in Section 7 shows lines 184→206 for double-commit bug.

---

## Document Status

**Version:** 2.0 (Corrected after characterization tests)
**Last Updated:** After all 9 characterization tests passing
**Blockers Resolved:** PostgreSQL running, real coverage measured, contradictions reconciled
**Next Step:** Execute Phase 1 extraction (input parser)

**Reviewed By:** Characterization tests (automated verification)
**Approved For:** Refactoring execution (all blockers cleared)
