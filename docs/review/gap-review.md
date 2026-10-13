# Gap review of the design handoff (2026-10-09)
Read-through only. Gaps and one contradiction; no LOCKED decision is challenged. Nothing in it was run or verified.

## Gaps that could cause real bugs
1. Current flag missing from the field contract. Sections 7 and 8 rely on current status and a partial unique index, but Section 5 has no is_current or equivalent. Add it.
2. Candidates and version numbers. A pending-review candidate gets no committed version number, so version_number must be NULL for candidates; the > 0 check and unique (logical_observation_key, version_number) must allow that. Decide whether candidates live in the observation table (with a state) or a separate review table. The unique key must include source_id, or the logical key must embed it, so two banks cannot collide.
3. Mapping issues versus immutability. Section 7 says to preserve the original result and record the corrected interpretation, but gives no mechanism. A supersede link would mislabel it as a bank correction, and a second current row would violate the one-current rule. Use a separate relation (for example reinterpretation_of_id) and a rule for which row the trusted view uses. Because raw responses are kept only conditionally, a valid-looking but wrongly mapped record cannot be re-parsed later; storing the source record's own JSON or text excerpt per observation addresses this. This is a tradeoff to decide, not a change to the locked policy.
4. Fingerprint stability. Add a fingerprint_version. If a mapping or normalization change alters hashes, every stored observation would look changed and flood the review queue. Define that comparisons happen under the same mapping version, or that old fingerprints are recomputed first. Clarify the scope of snapshot_fingerprint: per observation or per whole source snapshot.
5. Fallback dates and identity. If collection_date_fallback ever feeds identity, an unchanged page looks like a new publication each day. Rule: fallback dates never participate in identity; those records are ambiguous.
6. Calendar, time zone, and units. Sources may publish dates in the Ethiopian calendar: define parsing rules and a test. Freshness for today must be evaluated in Africa/Addis_Ababa. Banks may not publish on weekends or holidays, which affects freshness thresholds. Add quote currency (presumably ETB) and per-unit multiplier fields, TO VERIFY per source.
7. Run overlap. Test 12 covers concurrent corrections, but nothing prevents two overlapping runs for one source. Add a one-running-run-per-source constraint and a rule for stuck running rows.
8. Contradiction. Section 5 says collection_run_id is required for collected observations, implying other kinds exist; Section 8 says every observation references a run. Decide whether non-collected observations are in scope.

## Smaller items
- Run status rules: define when per-record rejections turn a run from success into partial_success.
- schema_fingerprint: marked optional, but the schema_change capture trigger cannot work without it. Make it required for API and HTML sources.
- suspicious_data needs a concrete definition (for example buying above selling, or a large jump).
- Verification roll-up: a source is verified only when every in-scope mapping is verified.
- Add a terms-of-use and polite request-rate review per source, especially for scraping.

## Open items: recommendations
- IDs: BIGINT identity, unless data will merge across databases.
- Precision: the rule is never silently rounded; decide scale from observed values and keep the original rate text so the parsed value can be checked.
- Raw retention: a bounded window (30 to 90 days) for content; hashes and metadata kept permanently.
- Freshness thresholds: leave undecided until each source's real publication pattern is seen.

## Acceptance tests to add
A. A to B to A revert: values return to an earlier version's values. This is a change versus current, so it goes to review and is not silently deduplicated.
B. Repeat candidates: the same changed value fetched repeatedly yields one candidate; a second different change while one is pending is handled.
C. Pending warning: a pending review on a logical observation shows an uncertainty warning on the current rate.
D. Mapping bump: a mapping or fingerprint version change creates no false correction candidates.
E. Excluded unknowns: unknown currency or category is excluded from the trusted view, not only flagged.
F. Dashen dates: per-table dates that differ are preserved separately.
G. Disappearing data: a previously populated source returning empty triggers the completeness warning.
H. Error bodies: HTTP 200 with an error body is treated as a failure.
I. Rate sanity: buying above selling raises a warning.
J. Date parsing: Ethiopian-calendar dates and Addis time zone boundaries are handled correctly.
K. Overlapping runs: runs for the same source cannot overlap, and a stale running row is recovered.
L. Provisional display: data from provisional sources is visibly labeled.
