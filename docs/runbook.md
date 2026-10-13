# Runbook

Three scenarios. Each has a trigger, a diagnosis step, and a resolution.

---

## 1. Stuck run

**Trigger**: A `collection_run` row has `status = 'running'` and `started_at` is more than 4 hours ago. The `uq_one_running_run_per_source` index blocks new runs for that source.

**Diagnose**:
```sql
SELECT id, source_id, started_at, status
FROM collection_run
WHERE status = 'running'
  AND started_at < now() - interval '4 hours';
```

**Resolve** (automated): `pipeline/runs.py::recover_stuck_run(conn, source_id)` marks the row `failed` with `error_code = 'stuck_run_recovered'`. The next scheduled run can then start.

**Resolve** (manual, if automation did not fire):
```sql
UPDATE collection_run
SET status = 'failed',
    finished_at = now(),
    error_code = 'stuck_run_recovered',
    error_summary = 'Manually recovered — exceeded 4-hour threshold'
WHERE id = <run_id>;
```

**After recovery**: check `alerts/checker.py::check_failed_runs` to confirm the alert fires, then re-trigger the collection for that source.

**Do not**: delete the stuck row. History is immutable. Do not touch any `rate_observation` rows.

---

## 2. Bank layout change

**Trigger**: `alerts/checker.py::check_schema_changes` fires, or a run finishes with `error_code = 'parse_failure'` or `schema_change`. A `raw_capture` row with `capture_reason = 'schema_change'` is present.

**Diagnose**:
```sql
SELECT rc.id, cr.source_id, rc.captured_at, rc.storage_reference
FROM raw_capture rc
JOIN collection_run cr ON cr.id = rc.collection_run_id
WHERE rc.capture_reason IN ('schema_change', 'parse_failure')
ORDER BY rc.captured_at DESC
LIMIT 10;
```
Retrieve the stored response from `storage_reference` and compare it against the adapter's fixture.

**Resolve**:
1. Fetch the bank's current page and save a new fixture in `fixtures/<bank>/normal.html` (or `.json`) with a timestamp comment.
2. Update `adapters/<bank>/adapter.py` to match the new layout.
3. Update `docs/mapping/<bank>.md` — change affected field statuses to `KNOWN` (re-verify before promoting to `VERIFIED`).
4. Run `python3 -m pytest tests/` — all tests must pass.
5. Update `rate_source.schema_fingerprint` for the source if the adapter uses it.
6. Re-enable the source and trigger a collection run.
7. Record an ADR in `docs/decisions/` if the layout change affects a LOCKED rule or a mapping decision.

**Do not**: silently update a mapping without recording the change. Do not mark fields `VERIFIED` from a single new capture.

---

## 3. Disputed rate

**Trigger**: A user or operator reports that a published rate does not match what the bank's official page shows, or `alerts/checker.py::check_schema_changes` / `validation_status = 'warning'` flags a suspicious value (e.g. buying > selling).

**Diagnose**:
```sql
-- Find the current observation for the disputed currency/source
SELECT o.id, o.source_id, o.currency_code, o.category_id,
       o.buying_rate, o.selling_rate, o.effective_date,
       o.identity_status, o.validation_status, o.change_review_status,
       o.source_rate_text, o.source_excerpt
FROM rate_observation o
WHERE o.is_current = TRUE
  AND o.source_id = <source_id>
  AND o.currency_code = '<CODE>'
ORDER BY o.effective_date DESC;

-- Check for open candidates
SELECT * FROM change_candidate
WHERE source_id = <source_id> AND status = 'open';
```

**Resolve — data quality issue on the bank's side** (buying > selling, obvious typo):
1. Use `review/workflow.py::decide_candidate` with `decision = 'dismissed'` and a reason.
2. The observation stays in the DB; the trusted view continues to show it with `validation_status = 'warning'`.
3. Record the finding in `docs/mapping/<bank>.md`.

**Resolve — genuine bank correction** (bank published a corrected rate):
1. Fetch the corrected page and save a new fixture.
2. Run the adapter — it will produce a new `AdapterRecord` with the corrected value.
3. The pipeline routes it to `change_candidate` with `status = 'open'`.
4. Use `review/workflow.py::decide_candidate` with `decision = 'confirmed_correction'`.
5. `pipeline/persist.py` creates a new `rate_observation` version linked by `supersedes_id` and sets `is_current = TRUE` on the new version.

**Resolve — mapping error** (wrong currency code or category assigned):
1. Create a corrected `rate_observation` with `reinterpretation_of_id` pointing to the original.
2. Use `review/workflow.py::decide_candidate` with `decision = 'mapping_issue'`.
3. Update `docs/mapping/<bank>.md` and bump `category_mapping_version` or `currency_mapping_version`.

**Do not**: overwrite `buying_rate` or `selling_rate` directly. Do not set `is_current = FALSE` manually without creating a superseding version. History is immutable.

---

## Production-readiness checklist

- [ ] Every enabled source has a `docs/mapping/<bank>.md` with a terms-of-use finding and a recorded request rate.
- [ ] Provisional sources are labeled `PROVISIONAL` in the UI and API response.
- [ ] Unverified fields are never shown as verified (`verification_status` surfaced in every API row).
- [ ] Database backup exists and a restore test has been run.
- [ ] `alerts/checker.py::run_all_checks` is scheduled (e.g. cron every hour) and its output is routed to an operator channel.
- [ ] Alerts exist for: failed runs, schema changes, disappearing data, rates older than `STALE_HOURS_DEFAULT` (26 h).
- [ ] This runbook covers: stuck run ✓, bank layout change ✓, disputed rate ✓.
