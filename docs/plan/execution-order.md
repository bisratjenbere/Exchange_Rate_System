# Execution order

Work top to bottom. Finish a step and record it in docs/plan/STATUS.md before starting the next. Steps marked (loop) repeat per item.

## Phase 0: Set up the workspace
1. Create the folders named in CLAUDE.md and the evidence, plan, decisions, mapping, register, and review folders under docs/.
2. Confirm the provided files are in place: handoff, gap review, defaults, source register, Addis capture.
3. Check the environment: language runtime, database, test runner. Fix what is missing. Record versions in STATUS.md.
4. Create STATUS.md and an empty ADR index.

## Phase 1: Reconcile and plan (milestone M0)
5. Read everything in the order given in the kickoff prompt.
6. Write docs/plan/00-kickoff-plan.md as the kickoff prompt describes. Adopt the defaults; list any you change with evidence.
7. Normalize the source register into a machine-readable form with one shape per bank. Keep every original status. Update the Addis entry as default 18 says.

## Phase 2: Evidence for Wave 1 (milestone M1)
8. (loop: CBE, Dashen, Addis) Run the per-source onboarding procedure below.
9. Investigate the CBE _limit parameter and the National Bank of Ethiopia question (defaults 16 and 17). Record findings.
10. Write docs/mapping/<bank>.md for each Wave 1 source with a status on every row.

## Phase 3: Schema (milestone M2)
11. Write the physical schema from the locked contract, the gap review, and the defaults.
12. Write constraint tests first: rate checks, version integrity, one current version per identified logical observation, status checks, run overlap guard, foreign keys.
13. Write migrations until those tests pass against a real database.
14. Record every schema decision as an ADR.

## Phase 4: Core pipeline (milestone M3)
15. Write tests first for acceptance tests 1 to 8 and 12 to 18, and for the gap-review tests on fingerprint versioning, revert (A to B to A), repeated candidates, pending warnings, and mapping version bumps.
16. Implement validation, normalization, fingerprinting, identity, deduplication, change-candidate routing, and the version and correction transaction until the tests pass.

## Phase 5: Wave 1 adapters, runs, trusted view (milestones M4 to M7)
17. (loop: Addis, CBE, Dashen) Write fixtures and adapter tests first, then the adapter. Dashen parses each table independently.
18. Implement collection runs: lifecycle, one running run per source, stuck-run recovery, raw capture triggers, diagnostics. Pass acceptance tests 9 to 11.
19. Implement the trusted-view read model with identity, validation, freshness, provisional labels, and uncertainty warnings. Pass acceptance tests 19 to 22 and the gap-review display tests.
20. Implement the review workflow: confirmed correction, new publication, mapping issue, dismissed, with actor, time, and reason.
21. Run the three adapters end to end against live sources politely. Schedule recurring collection so measured data accumulates.

## Phase 6: Waves 2 to 5 (milestone M4, repeated)
22. (loop: each bank in Wave 2, then 3, then 4, then 5) Run the per-source onboarding procedure, then build the adapter. Reuse a shared adapter family where the structure matches, with per-source configuration. Never put bank-specific conditions into shared persistence code.
23. Wave 4: find the official exchange-rate page or endpoint first. If none exists, record that and mark the source unresolved.
24. Wave 5: apply defaults 2 and 15 and the blocked-source rule. Unresolved banks stay unresolved and are recorded as such.

## Phase 7: Presentation and operations (milestone M8)
25. Build the read API and a minimal interface showing effective date and last fetch separately, with provisional and uncertainty labels.
26. Add alerts for failed runs, schema changes, disappearing data, and rates older than the configured limit.
27. Write the runbook and meet the production-readiness checklist below.

## Phase 8: Harden with real data
28. After at least 14 days of collected data, measure each source's publication pattern and propose freshness thresholds as an ADR.
29. Review suspicious-data and review-queue volume. Tune rules without weakening locked ones.
30. Promote sources from provisional to verified or validated only by the evidence rules in CLAUDE.md. Update the register honestly.

## Per-source onboarding procedure (use for every bank)
1. Read the register entry and its requires_verification list.
2. Check terms of use and robots rules. Record the finding. If access is forbidden, set BLOCKED and stop this source.
3. Fetch politely: identified user agent, rate limit, timeout. Save the response as a fixture with a timestamp and the exact request.
4. Decide the collection method: structured response, static HTML, or browser rendering. For POST endpoints, work out how the official page builds the request, including any nonce.
5. Document every field or selector with an example value in docs/mapping/<bank>.md. Do not copy names from another bank.
6. Determine date semantics, calendar, time zone, identity capabilities, quote currency, unit multiplier, and empty and error behavior.
7. Compare with the official publication as CLAUDE.md describes. Set row statuses from the evidence.
8. Build fixtures: normal, empty, malformed or schema-changed, unknown currency, unknown category, duplicate fetch, and partial failure where applicable.
9. Write the adapter tests first. Then implement the adapter until they pass.
10. Run the adapter once end to end and inspect the stored results for ambiguity and rejections.
11. Update the register entry and the source verification status honestly.
12. Write the STATUS.md entry for this source.

## Production-readiness checklist (end of Phase 7)
- Every enabled source has a recorded terms-of-use finding and a request rate within it.
- Provisional sources are visibly labeled, and unverified fields never appear as verified.
- Backups and a restore test exist for the database.
- Alerts exist for failed runs, schema changes, and rates older than the configured freshness limit.
- A runbook covers a stuck run, a bank layout change, and a disputed rate.
