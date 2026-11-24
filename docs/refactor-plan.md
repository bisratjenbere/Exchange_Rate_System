# Refactor Plan — Exchange Rate Pipeline

_Revised after re-verifying every finding and applying all amendments._

---

## 1. Summary

This plan fixes 8 verified findings from the code review in 7 independent work packages.
The changes fall into three tiers: (1) golden and characterization tests that pin current
behaviour before anything is touched, (2) data-integrity fixes that close atomicity gaps
and race conditions, and (3) a structural clean-up that wires the production entry point
to the already-tested `Scheduler` class. One package requires a DB backfill; it is
isolated with a backup-and-restore rollback strategy. No new architectural layers are
introduced. Total packages: **7 (P1 – P7)**. Estimated calendar order:
P1 → P2/P3/P4 in parallel → P5 → P6 → P7.

---

## 2. Invalidated Findings

| Finding | Reason dropped |
|---------|---------------|
| **C-3 — INSERT/UPDATE order in the "changed" path** | Re-verified: the `UPDATE rate_observation SET is_current = FALSE WHERE id = %s` at `pipeline/ingest.py:168` and the `insert_observation` call at `pipeline/ingest.py:189` both execute inside the savepoint opened at line 41 (`SAVEPOINT _ingest_sp`). A crash between the two statements causes `ROLLBACK TO SAVEPOINT _ingest_sp` at line 49, which undoes both the UPDATE and any partial work — there is no gap. Furthermore, inserting the new row with `is_current = TRUE` before retiring the old one would immediately violate `uq_one_current_per_logical_key`. The finding is invalid. Replaced with a verification-only test (see P3). |
| **H-3 — `runs.py` uses server clock `now()` for `started_at`** | `reap_stuck_runs` passes a Python-computed `threshold` as a bound parameter (`WHERE started_at < %s`, `pipeline/runs.py:57`), so the comparison is always Python-clock vs. DB-stored value. The skew risk is real but no concrete failure has been observed on a single-region deployment. Excluded. |
| **L-1 — `finish_run` has 11 parameters** | All call sites already use keyword arguments. No correctness risk. Excluded. |

---

## 3. Decisions Needed

### D-1 — Fingerprint backfill feasibility and scope (affects P5)

**Traced finding:** `classify_observation` (`pipeline/deduplicate.py:8-10`) queries
`snapshot_fingerprint` with no `fingerprint_version` filter:
```sql
SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1
```
After a version bump, a row ingested with the new logic will never match an old row
stored with the old logic for the same rate. Without a backfill, every previously-seen
rate is re-ingested as "new" on the first post-deploy run.

**Can fingerprints be recomputed from stored data?**

The fingerprint payload (`pipeline/fingerprint.py:13-23`) uses:
- `v` — constant, known
- `source_id` — stored column `rate_observation.source_id`
- `collection_date` — derivable as `fetched_at::date` (`rate_observation.fetched_at`, stored)
- `source_currency_code` — stored column
- `category` — **the raw string** (e.g. `"cash"`), not `category_id`. The raw string is
  NOT stored in `rate_observation`; only `category_id` (FK) is stored
  (`db/migrations/001_initial_schema.sql:85`). It can be recovered via
  `JOIN rate_category rc ON rc.id = ro.category_id` using `rc.code`. Rows with
  `category_id IS NULL` (UNKNOWN category) stored `record.category = "UNKNOWN"` at
  ingest time — this must be hardcoded as `"UNKNOWN"` in the backfill for those rows.
- `effective_date` — stored column
- `buying_rate` / `selling_rate` — stored columns (as `NUMERIC(24,10)`)
- `source_publication_key` — stored column (`001_initial_schema.sql:112`)

**Conclusion:** All fields are recoverable from stored data. A Python backfill script
can recompute fingerprints. The `buying_rate` / `selling_rate` values must be read back
as `Decimal` from the DB and formatted with the new canonical rule
(`format(d.normalize(), "f")`), which is the same transformation the fixed code applies.

**Options:**
- **A (recommended):** Backfill all existing rows before deploying the new code. Take a
  backup of `(id, snapshot_fingerprint, fingerprint_version)` before running so rollback
  is a simple `UPDATE … FROM backup_table`.
- **B:** Add a `fingerprint_version` filter to `classify_observation` and skip the
  backfill. This permanently complicates deduplication and allows two rows for the same
  rate to coexist under different versions.

**Recommended default:** Option A. The backfill is a pure UPDATE with no schema change.
The backup table makes rollback deterministic.

**Impact if wrong (Option B chosen):** Every source produces a wave of spurious "new"
observations on the first post-deploy run. The partial unique index
`uq_one_current_per_logical_key` turns these into constraint errors for confirmed-key
sources, so data is not silently corrupted, but every such run fails until reconciled.

---

### D-2 — `_retire_prior_fallback_observations` category filter (affects P4)

**Question:** The second arm of the OR at `pipeline/ingest.py:247` retires non-fallback
rows with an older `effective_date` for the same `category_id`. Should the category
filter be kept?

**Evidence from existing tests:**
`test_native_success_retires_prior_fallback_across_all_categories`
(`tests/test_fallback_guardrails.py:246-290`) asserts that a native observation for
`category="transactional"` retires **both** the fallback cash and fallback transactional
rows. This test passes today because the `is_fallback = TRUE` arm of the OR (no category
filter) catches both. The category filter only applies to the second arm (non-fallback
rows). Removing the category filter from the second arm would retire non-fallback rows
across all categories — which is not the intent and would break
`test_native_newer_date_does_not_retire_different_category_active`
(`tests/test_fallback_guardrails.py:316-349`).

**Recommended default:** Keep the category filter on the second arm. The fix in P4
narrows the second arm to `is_fallback = FALSE` callers only, while leaving the category
filter intact.

---

### D-3 — Legacy `run_source` / `run_all` cutover (affects P7)

**Question:** Is the module-level `run_all` at `scheduler/runner.py:514` (called by
`scheduler/run_job.py:13`) intentionally kept as the production path, or is it an
oversight?

**Options:**
- **A (recommended):** Oversight. Wire `run_job.py` to `Scheduler` and delete the legacy
  functions. The `Scheduler` class uses the circuit breaker
  (`runner.py:88, 256, 275`) and injected `ErrorClassifier`; the legacy path does not.
- **B:** Intentional. Keep both paths and document the distinction.

**Recommended default:** Option A. Any fix applied to `Scheduler.run_source` is silently
absent from the production entry point today.

**Impact if wrong (Option B chosen):** P7 is skipped. The circuit breaker continues to
have no effect in production.

---

### D-4 — `StaleObservationError`: re-raise vs. return `None` (affects P6)

**Question:** When `commit_correction` detects that the prior observation is no longer
`is_current`, should `decide_candidate` re-raise `StaleObservationError` to the caller,
or catch it and return `None`?

**Options:**
- **A (recommended — re-raise):** The caller (a human review UI or API endpoint) must
  know the correction was not applied so it can show an error and prompt the reviewer to
  re-examine the candidate. Silently returning `None` is indistinguishable from a
  non-correction decision path and would leave the candidate in `confirmed_correction`
  status with no new observation created.
- **B (return `None`):** Simpler caller contract, but creates the silent half-applied
  state described above.

**Recommended default:** Option A — re-raise. The candidate UPDATE and
`change_review_status` UPDATE are inside the same transaction as `commit_correction`
(after P2 removes the intermediate commit), so a re-raise causes the whole transaction
to roll back, leaving the candidate in its original `open` state. The reviewer can retry.

---

## 4. Work Packages

---

### P1 — Golden tests: pin fingerprint behaviour and add Scheduler characterization tests

- **Fixes:** Review test gaps 1 (fingerprint determinism) and 5 (Scheduler path
  characterization before P7 cutover).
- **Files touched:** `tests/test_m3_pipeline.py`, `tests/test_m10_ingest_scheduler.py`
- **Change description:**
  1. In `tests/test_m3_pipeline.py`, add a golden test that calls `compute_fingerprint`
     with a fixed `AdapterRecord` (e.g. `buying_rate=Decimal("161.00")`,
     `selling_rate=Decimal("164.00")`, `source_currency_code="USD"`,
     `category="cash"`, `effective_date=date(2024, 1, 15)`), `source_id=1`, and
     `collection_date=date(2024, 1, 15)`, and asserts the output equals a pinned hex
     string. Also assert that `Decimal("1.5")` and `Decimal("1.5000")` produce
     **different** hashes — documenting the current broken behaviour that P5 must fix.
     This test is expected to fail after P5, which is the signal P5 is working.
  2. In `tests/test_m10_ingest_scheduler.py`, add characterization tests for
     `Scheduler.run_source` (not the legacy `run_source`) covering: (a) fallback
     invoked when primary returns zero records — assert `Scheduler.run_source` calls
     `_try_af_fallback` and returns `fallback: "addis_fortune"`; (b) circuit breaker
     open — assert `Scheduler.run_source` returns `status: "skipped"` when
     `circuit_breaker.should_attempt` returns `False`; (c) circuit breaker records
     failure on HTTP error — assert `circuit_breaker.record_failure` is called. Use a
     mock `CircuitBreaker` injected via `Scheduler(circuit_breaker=mock_cb)`.
- **Behavior change:** None — tests only.
- **Data safety:** No stored data affected.
- **DB migration:** None.
- **Verification:** `pytest tests/test_m3_pipeline.py -k golden` and
  `pytest tests/test_m10_ingest_scheduler.py -k scheduler` — all new tests pass.
  The golden Decimal test must pass (pinning current broken behaviour).
- **Risk:** Low — tests only.
- **Effort:** S
- **Depends on:** Nothing.

---

### P2 — Fix split-commit atomicity in `decide_candidate`

- **Fixes:** C-4 — `decide_candidate` (`review/workflow.py:67`) commits after updating
  `change_candidate` and `rate_observation.change_review_status`, then calls
  `commit_correction`, then commits again at line 82. A crash between the two commits
  leaves the candidate marked `confirmed_correction` with no new observation.
- **Files touched:** `review/workflow.py`
- **Change description:** Remove the `conn.commit()` at `review/workflow.py:67`. The
  `conn.commit()` at line 82 becomes the single commit for the entire
  `confirmed_correction` path, making the candidate status update, the
  `change_review_status` update, and the new observation INSERT atomic. For all other
  decision paths the `conn.commit()` at line 85 is unchanged. `commit_correction`
  (`pipeline/persist.py:75-157`) does not call `conn.commit()` — confirmed by
  inspection — so no change is needed there.
- **Behavior change:** Internal only — the observable outcome is identical; only the
  failure mode changes.
- **Data safety:** No stored data affected. Existing rows are not touched.
- **DB migration:** None.
- **Verification:** Add a test in `tests/test_m7_runs_trusted_review.py`: seed a
  candidate, call `decide_candidate` with `decision="confirmed_correction"` but make
  `commit_correction` raise (by passing a `prior_obs_id` that does not exist), then
  assert that the `change_candidate` status update was **not** persisted — i.e. the
  candidate row still has `status = "open"` in a fresh query after the exception.
  This directly tests that the intermediate commit is gone. Also run
  `test_review_confirmed_correction_via_workflow` to confirm the happy path passes.
- **Risk:** Low — one line removed, no schema change.
- **Effort:** S
- **Depends on:** P1.

---

### P3 — Verification test: savepoint rolls back both writes in the "changed" path

- **Fixes:** C-3 was invalidated (see §2). This package replaces it with a test that
  documents and guards the savepoint guarantee.
- **Files touched:** `tests/test_m10_ingest_scheduler.py`
- **Change description:** Add a test that: (1) seeds a current observation for a logical
  key; (2) calls `ingest` with a "changed" record for the same key but arranges for
  `insert_observation` to raise (e.g. by passing a `run_id` that references a
  non-existent `collection_run`); (3) asserts that the original row still has
  `is_current = TRUE` — i.e. the `UPDATE … SET is_current = FALSE` at
  `pipeline/ingest.py:168` was rolled back by `ROLLBACK TO SAVEPOINT _ingest_sp` at
  line 49. This pins the savepoint guarantee so any future refactor that breaks it is
  caught immediately.
- **Behavior change:** None — test only.
- **Data safety:** No stored data affected.
- **DB migration:** None.
- **Verification:** `pytest tests/test_m10_ingest_scheduler.py -k savepoint` — test
  passes.
- **Risk:** Low — test only.
- **Effort:** S
- **Depends on:** P1.

---

### P4 — Narrow `_retire_prior_fallback_observations` to fallback rows only for non-fallback callers

- **Fixes:** M-5 — the OR condition at `pipeline/ingest.py:247`:
  ```sql
  AND (is_fallback = TRUE
       OR (category_id IS NOT DISTINCT FROM %s AND effective_date < %s))
  ```
  The second arm retires non-fallback rows with an older `effective_date` for the same
  category. When a non-fallback "new" observation arrives, this can retire a legitimate
  standing non-fallback rate that simply has an older date.
- **Files touched:** `pipeline/ingest.py`
- **Change description:** Add an `is_fallback: bool` parameter to
  `_retire_prior_fallback_observations` (`pipeline/ingest.py:237`). When
  `is_fallback=True` (the caller is itself a fallback), execute only the first arm —
  retire `is_fallback = TRUE` rows for the same source and currency, with no category
  or date filter, because a newer fallback should supersede all older fallbacks
  regardless of category. When `is_fallback=False`, execute both arms as today,
  keeping the category filter on the second arm (required by
  `test_native_newer_date_does_not_retire_different_category_active`,
  `tests/test_fallback_guardrails.py:316-349`). Thread the `is_fallback` argument
  through from the two call sites: `pipeline/ingest.py:98` (duplicate path, always
  `is_fallback=False` at that point since the guard is `if not is_fallback`) and
  `pipeline/ingest.py:187` (new/changed path, pass the `is_fallback` parameter
  already in scope).
- **Behavior change:** Internal only — the narrowed SQL retires fewer rows when a
  fallback observation arrives alongside an existing fallback row of a different
  category. The non-fallback path is unchanged.
- **Data safety:** No stored data affected. The change is strictly more conservative
  for the fallback caller path.
- **DB migration:** None.
- **Verification:** Add a test: seed one fallback current row (category=cash) and one
  non-fallback current row (category=cash, older effective date) for the same
  source/currency. Call `_retire_prior_fallback_observations` with a newer effective
  date and `is_fallback=True`. Assert only the fallback row has `is_current = FALSE`
  and the non-fallback row is untouched. Run the full `test_fallback_guardrails.py`
  suite — all existing tests must pass, confirming the non-fallback path is unchanged.
- **Risk:** Low — SQL change is strictly more conservative on the fallback path;
  non-fallback path is identical to today.
- **Effort:** S
- **Depends on:** P1, D-2 confirmed.

---

### P5 — Fix non-deterministic fingerprint: remove hidden clock, canonicalize Decimal, add `unit_multiplier` and `quote_currency_code`

- **Fixes:** H-1 (both parts — `datetime.now()` default at `pipeline/fingerprint.py:10-11`
  and non-canonical `Decimal` serialization at lines 20-21); H-2 (`unit_multiplier` and
  `quote_currency_code` absent from payload).
- **Files touched:** `pipeline/fingerprint.py`,
  `db/migrations/006_recompute_fingerprints.sql`,
  `scripts/backfill_fingerprints.py` (new script)
- **Change description:**
  1. Remove the `if collection_date is None: collection_date = datetime.now().date()`
     fallback at `fingerprint.py:10-11`. Make `collection_date` a required positional
     parameter (drop the `= None` default). The single call site at
     `pipeline/ingest.py:77` already passes `fetched_at.date()` — no caller change
     needed.
  2. Replace `str(record.buying_rate)` and `str(record.selling_rate)` at lines 20-21
     with `format(record.buying_rate.normalize(), "f")` (and same for `selling_rate`).
     This canonicalises `Decimal("1.50")` and `Decimal("1.5000")` both to `"1.5"`.
  3. Add `"unit_multiplier": str(record.unit_multiplier)` and
     `"quote_currency_code": record.quote_currency_code` to the payload dict.
  4. Bump `FINGERPRINT_VERSION` from `2` to `3`.
  5. Write `scripts/backfill_fingerprints.py` and migration stub
     `db/migrations/006_recompute_fingerprints.sql` (see DB migration section).

  P5 and the former P6 are merged into one package with a single version bump to `3`,
  as directed. A single backfill is cheaper and safer than two sequential backfills.

- **Behavior change:** Affects stored data — `snapshot_fingerprint` values for all
  existing rows are recomputed by the backfill script.

- **Data safety:**
  Before running the backfill, create a backup table:
  ```sql
  CREATE TABLE fingerprint_backup_v2 AS
  SELECT id, snapshot_fingerprint, fingerprint_version
  FROM rate_observation;
  ```
  The backfill script updates rows in batches of 500, sleeping 50 ms between batches.
  Rollback restores from the backup table:
  ```sql
  UPDATE rate_observation ro
  SET snapshot_fingerprint = b.snapshot_fingerprint,
      fingerprint_version  = b.fingerprint_version
  FROM fingerprint_backup_v2 b
  WHERE ro.id = b.id;
  DROP TABLE fingerprint_backup_v2;
  ```
  The backup table must be kept until the first full collection cycle after deployment
  completes without errors.

- **DB migration:**
  ```sql
  -- 006_recompute_fingerprints.sql (intent record only — actual UPDATE via script)

  -- Pre-check: count rows to be updated
  SELECT COUNT(*) FROM rate_observation WHERE fingerprint_version < 3;

  -- Backup (run before script):
  CREATE TABLE fingerprint_backup_v2 AS
  SELECT id, snapshot_fingerprint, fingerprint_version FROM rate_observation;

  -- Backfill run via:
  --   python scripts/backfill_fingerprints.py --dry-run
  --   python scripts/backfill_fingerprints.py

  -- Post-check: must be 0
  SELECT COUNT(*) FROM rate_observation WHERE fingerprint_version != 3;

  -- Rollback (if needed):
  UPDATE rate_observation ro
  SET snapshot_fingerprint = b.snapshot_fingerprint,
      fingerprint_version  = b.fingerprint_version
  FROM fingerprint_backup_v2 b WHERE ro.id = b.id;
  DROP TABLE fingerprint_backup_v2;
  ```
  Lock impact: the backfill script issues row-level UPDATE statements in batches; no
  DDL, no table lock, no index rebuild. The `snapshot_fingerprint` column has no unique
  index (only `uq_one_current_per_logical_key` and `uq_version_per_logical_key` exist),
  so there is no index contention during the UPDATE.

  **Backfill feasibility — verified:** All fields in the fingerprint payload are
  recoverable from stored columns. `category` (raw string) is recovered via
  `JOIN rate_category rc ON rc.id = ro.category_id` using `rc.code`; rows with
  `category_id IS NULL` use the hardcoded string `"UNKNOWN"`.
  `collection_date` is recovered as `ro.fetched_at::date`. All other fields
  (`source_id`, `source_currency_code`, `effective_date`, `buying_rate`,
  `selling_rate`, `source_publication_key`, `unit_multiplier`, `quote_currency_code`)
  are stored directly in `rate_observation`
  (`db/migrations/001_initial_schema.sql:83-112`).

- **Verification:**
  1. The golden test added in P1 (asserting `Decimal("1.5")` ≠ `Decimal("1.5000")`)
     must now **fail** — update it to assert they produce the **same** hash and pin the
     new expected hex value.
  2. Add a test: two records identical except `unit_multiplier=1` vs `unit_multiplier=100`
     must produce different fingerprints.
  3. `pytest tests/test_m3_pipeline.py -k fingerprint` — all fingerprint tests pass.
  4. After backfill:
     `SELECT COUNT(*) FROM rate_observation WHERE fingerprint_version != 3;` — must be 0.
  5. After first post-deploy collection run: no source reports a wave of "new"
     observations for previously-seen rates.

- **Risk:** Medium — changes stored fingerprint values. Mitigated by the backup table
  (deterministic rollback) and the `--dry-run` mode on the backfill script.
- **Effort:** M
- **Depends on:** P1, P2, P3, P4 (all correctness fixes in place before touching stored
  data).

---

### P6 — Fix `commit_correction`: derive version from locked row; add `StaleObservationError`

- **Fixes:** C-1 — `commit_correction` at `pipeline/persist.py:96-105` locks the prior
  row with `SELECT … FOR UPDATE` but then computes `new_version = prior_version_number + 1`
  from the caller-supplied argument (`persist.py:105`). The caller
  (`review/workflow.py:61-65`) read `version_number` before the lock was taken. A
  concurrent correction between the read and the lock produces a stale argument and a
  duplicate or wrong version number.
- **Files touched:** `pipeline/persist.py`, `review/workflow.py`, `domain/exceptions.py`
  (new file — one class, justified because callers need to distinguish a stale-lock
  failure from a generic `ValueError` to decide whether to retry or surface an error).
- **Change description:**
  1. Create `domain/exceptions.py`:
     ```python
     class StaleObservationError(Exception):
         """Raised when commit_correction finds the prior row is no longer is_current."""
     ```
  2. In `commit_correction` (`persist.py:96`), extend the `SELECT … FOR UPDATE` to also
     fetch `is_current` and `version_number`:
     ```sql
     SELECT id, logical_observation_key, is_current, version_number
     FROM rate_observation WHERE id = %s FOR UPDATE
     ```
     After the fetch, if `is_current` is `False`, raise `StaleObservationError`.
     Compute `new_version` from the locked row's `version_number`, not from the
     parameter. Remove the `prior_version_number` parameter from the function signature.
  3. In `review/workflow.py`, remove the separate `SELECT version_number` query at
     lines 59-65 — the version is now read inside `commit_correction` from the locked
     row. Remove `prior_version_number` from the `commit_correction` call at line 80.
     Per D-4, let `StaleObservationError` propagate to the caller (re-raise); because
     the intermediate `conn.commit()` was removed in P2, the whole transaction rolls
     back and the candidate remains `open`.
  4. Update `test_5_confirmed_correction_creates_new_version`
     (`tests/test_m3_pipeline.py`) and `test_review_confirmed_correction_via_workflow`
     (`tests/test_m7_runs_trusted_review.py`) to remove the `prior_version_number`
     argument.
- **Behavior change:** Internal only — stale corrections now raise and roll back instead
  of writing a wrong version number. The happy path is unchanged.
- **Data safety:** No stored data affected. Existing rows are not touched.
- **DB migration:** None.
- **Verification:**
  1. Add a test: seed a row with `version_number=1, is_current=FALSE`. Call
     `commit_correction` targeting that row. Assert `StaleObservationError` is raised
     and no new row was inserted.
  2. Add a test: seed a row with `version_number=1, is_current=TRUE`. Call
     `commit_correction`. Assert the new row has `version_number=2` and the old row
     has `is_current=FALSE`.
  3. Run `test_5_confirmed_correction_creates_new_version` and
     `test_review_confirmed_correction_via_workflow` — both must pass without
     `prior_version_number`.
- **Risk:** Medium — changes the signature of `commit_correction`. All callers are in
  this repo and are updated in the same commit.
- **Effort:** S
- **Depends on:** P2 (intermediate commit removed first, so `StaleObservationError`
  propagation causes a clean rollback).

---

### P7 — Wire `run_job.py` to `Scheduler`; delete legacy module-level functions

- **Fixes:** H-4 — `scheduler/run_job.py:13` imports and calls the legacy `run_all`
  at `scheduler/runner.py:514`, which bypasses the circuit breaker
  (`runner.py:88, 256, 275`), the injected `ErrorClassifier`, and
  `RateSourceRepository`. Any fix applied to `Scheduler.run_source` is silently absent
  from the production entry point.
- **Files touched:** `scheduler/run_job.py`, `scheduler/runner.py`,
  `tests/test_m10_ingest_scheduler.py`, `tests/test_fallback_guardrails.py`
- **Change description:**
  1. In `run_job.py`, replace `from scheduler.runner import run_all` with
     `from scheduler.runner import Scheduler`. Instantiate `Scheduler()` and call
     `scheduler.run_all(conn)`.
  2. In `runner.py`, delete the following functions which become dead code after step 1:
     `run_source` (line 321), `run_all` (line 514), `_load_source_old` (line 588),
     `_load_enabled_sources_old`, `_check_schema_old`, `_update_fingerprint_old`,
     `_update_last_success_old` (line 652), `_try_af_fallback_old` (line 659),
     `_classify_error` (line 546), `_load_adapter` (line 525).
     Keep all functions used by `Scheduler.run_source`: `_fetch_with_retry`,
     `_has_fetch_raw`, `_fetch`, `_fetch_browser`, `_build_url`, `_parse`,
     `_check_schema`, `_store_raw_capture`, `_run_status`, `_reset_failure_counter`,
     `_increment_failure_counter`, `_write_alert`, `_try_af_fallback`,
     `_expire_stale_fallback_current`.
  3. `tests/test_m10_ingest_scheduler.py:287` imports
     `run_source, run_all, _load_adapter, _parse, _run_status, _classify_error`
     from `scheduler.runner`. After deletion: keep `_parse` and `_run_status` (still
     present); replace `run_source` / `run_all` tests with `Scheduler`-based equivalents
     using a mock `AdapterRegistry`; replace `_load_adapter` tests with
     `AdapterRegistry.get` tests; replace `_classify_error` tests with
     `ErrorClassifier.classify` tests.
  4. `tests/test_fallback_guardrails.py:378-383` and `458-463` patch
     `scheduler.runner._fetch`, `scheduler.runner._load_adapter`, and import
     `run_source` from `scheduler.runner`. Rewrite these two tests to use
     `Scheduler(adapter_registry=mock_registry, ...)` directly, removing the
     dependency on the legacy helpers.
- **Behavior change:** The production entry point now uses the circuit breaker
  (`failure_threshold=3, recovery_timeout=300s` by default,
  `infrastructure/circuit_breaker.py:29-33`). **This is a production behaviour change:**
  after 3 consecutive failures for an adapter key, `Scheduler.run_source` will skip that
  source for up to 300 seconds and attempt the Addis Fortune fallback instead
  (`runner.py:88-97`). The legacy path never skipped a source. Operators should be aware
  that a source that was previously retried on every run will now be skipped during the
  recovery window. Monitor `source_alert` and logs on the first post-deploy run.
- **Data safety:** No stored data affected.
- **DB migration:** None.
- **Verification:**
  1. Run `pytest tests/test_m10_ingest_scheduler.py tests/test_fallback_guardrails.py`
     — all tests pass after patch targets are updated.
  2. `python -m scheduler.run_job` in a dry-run environment completes without import
     errors.
  3. `grep -r "from scheduler.runner import run_all" .` returns no results.
  4. `grep -r "from scheduler.runner import run_source" .` returns no results outside
     of any remaining test helpers.
- **Risk:** High — changes the production entry point and activates the circuit breaker
  for the first time. The circuit breaker is in-memory and resets on process restart,
  so a bad deploy can be recovered by restarting the scheduler process. Roll back by
  reverting the `run_job.py` import change.
- **Effort:** M
- **Depends on:** P1 (Scheduler characterization tests in place), P3, P4, P6.

---

### Low-priority clean-up (not scheduled in this plan)

The following findings are valid but carry no correctness risk and are deferred until
the above packages are merged and stable:

- **M-1** (duplicate 26-column INSERT in `persist.py`) — DRY refactor, no behaviour
  change.
- **M-2** (`_process_one` length and duplication) — readability refactor.
- **M-3** (`EffectiveDateBasis` enum adoption) — naming refactor.
- **M-4** (`__import__('re')` and non-finite Decimal in `normalize.py`) — the
  non-finite Decimal gap (`NaN`, `Infinity`) is blocked by the DB `NUMERIC` column
  constraint, which raises `DataError` rather than silently storing a bad value. Fix
  it, but it is not urgent.
- **L-2** (category normalizer `__main__` block) — move to pytest, delete block.
- **L-3** (`_build_url` magic strings and `date.today()`) — move URL logic into
  adapters.

---

## 5. Dependency Graph

```
P1 (golden + Scheduler characterization tests)
├── P2 (split-commit fix)              — depends on P1
├── P3 (savepoint verification test)   — depends on P1
└── P4 (retire fallback narrowing)     — depends on P1, D-2

P2, P3, P4 complete
└── P5 (fingerprint: clock + Decimal + unit_multiplier) — depends on P1, P2, P3, P4

P2 complete
└── P6 (commit_correction locking + StaleObservationError) — depends on P2

P1, P3, P4, P6 complete
└── P7 (wire run_job to Scheduler)     — depends on P1, P3, P4, P6
```

Packages that can run in parallel once their shared dependency is met:
- **P2, P3, P4** can be developed in parallel after P1 merges (different files,
  no shared state).
- **P5 and P6** can be developed in parallel after P2 merges; P5 also requires P3
  and P4.
- **P7** must wait for P1, P3, P4, and P6.

---

## 6. Rollout Order for Production

### Phase 1 — Tests only (no downtime, no migration)
Merge P1. Confirm CI is green. This is the safety net for everything that follows.

### Phase 2 — Atomicity and narrowing fixes (no downtime, no migration)
Merge P2, P3, P4 together in one release. All three are pure Python changes with no
schema impact. Run the full test suite before deploying. No maintenance window needed.

### Phase 3 — Fingerprint version bump (requires backfill, brief maintenance window)
1. Run `python scripts/backfill_fingerprints.py --dry-run` to verify row counts.
2. Create the backup table:
   `CREATE TABLE fingerprint_backup_v2 AS SELECT id, snapshot_fingerprint, fingerprint_version FROM rate_observation;`
3. Schedule a maintenance window (pause collection via `CollectionControl`).
4. Run `python scripts/backfill_fingerprints.py` (batched UPDATEs).
5. Verify: `SELECT COUNT(*) FROM rate_observation WHERE fingerprint_version != 3;` → 0.
6. Deploy the P5 code change.
7. Resume collection. Monitor the first run: all previously-seen rates must be
   classified as duplicates, not "new". If any source produces a wave of "new"
   observations, pause collection, run the rollback SQL from the backup table, and
   revert the code deploy before investigating.
8. Once the first clean run completes: `DROP TABLE fingerprint_backup_v2;`

### Phase 4 — Correction locking fix (no downtime, no migration)
Merge P6. Pure Python change. No maintenance window needed.

### Phase 5 — Entry point cutover (no downtime, no migration, but behaviour change)
Merge P7. Monitor the first full collection run via logs to confirm the circuit breaker
is active and no source is unexpectedly skipped. The circuit breaker state is in-memory
and resets on process restart, so a bad deploy is recoverable by restarting the
scheduler. Roll back by reverting the `run_job.py` import change if unexpected skipping
is observed.

---

## 7. Definition of Done

The refactor is complete when all of the following are true:

1. All 7 packages (P1–P7) are merged to the main branch.
2. `pytest` passes with zero failures and zero errors across the full test suite.
3. `SELECT COUNT(*) FROM rate_observation WHERE fingerprint_version != 3;` returns 0.
4. `grep -rn "datetime.now().date()" pipeline/fingerprint.py` returns no results.
5. `grep -rn "prior_version_number" pipeline/persist.py review/workflow.py` returns no
   results.
6. `grep -rn "from scheduler.runner import run_all" .` returns no results.
7. `grep -rn "from scheduler.runner import run_source" .` returns no results outside
   of any remaining test helpers.
8. One full production collection cycle completes after P7 is deployed with no sources
   reporting unexpected "new" observations for previously-seen rates and no sources
   unexpectedly skipped by the circuit breaker.
9. `fingerprint_backup_v2` has been dropped after the first clean post-P5 run.
10. The deferred clean-up items (M-1, M-2, M-3, M-4, L-2, L-3) are tracked in the
    issue tracker with "tech-debt" labels.
