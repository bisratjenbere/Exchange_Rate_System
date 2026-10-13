# Decisions already made for the agent

These are recommendations adopted so the agent is never blocked on a question. The agent may change one only by recording an ADR (a short decision record in docs/decisions/) that cites evidence, and may never use a default to weaken a LOCKED rule. Edit any row to override it.

| # | Decision | Default | Reason |
| --- | --- | --- | --- |
| 1 | Category `other` from the register | Not adopted. Four approved categories only; unknown categories use the unknown-category flag | A catch-all would let unclassified rates into the trusted view |
| 2 | Third-party mirrors (Anbesa, Shabelle) | Add a source authority field (official or third_party). Mirror sources are disabled by default and never feed the trusted official view | The register's own rule keeps third-party data separate |
| 3 | Non-collected observations (manual or backfilled) | Out of scope. Every observation references a collection run | Resolves the handoff's inconsistency; revisit only if a backfill need appears |
| 4 | Where review candidates live | Changed-value candidates go in a separate change-candidate table. Ambiguous-identity records stay in the observation table with identity status ambiguous and no committed version | Keeps version constraints simple while following the handoff |
| 5 | Mapping reinterpretation | A separate reinterpretation link, never supersedes_id and never a second current row. The trusted view uses the reinterpreted row | Prevents a parser fix from being mislabeled as a bank correction |
| 6 | Per-observation source excerpt | Keep the source record's own JSON or text excerpt, size-limited, on each observation | Lets a wrongly mapped record be re-parsed without retaining full responses |
| 7 | ID convention | BIGINT identity | Simplest, unless data must merge across databases |
| 8 | Rate precision | Start with NUMERIC(24,10) and keep the original rate text. Confirm after Wave 1 captures show no rounding | Addis returns 4 decimal places; other banks are not yet seen |
| 9 | Quote currency and unit | Add quote currency and unit multiplier fields, both TO VERIFY per source | The captured sources state neither |
| 10 | Raw capture retention | Content for 90 days; hashes and metadata kept permanently | Bounded storage with a permanent audit trail |
| 11 | Freshness thresholds | None hardcoded. Show effective date and age; after at least 14 days of collected data, propose per source and category thresholds from measured patterns | The handoff says thresholds must come from evidence |
| 12 | Time zone and calendar | Freshness uses Africa/Addis_Ababa. One tested function parses Ethiopian-calendar dates | Banks may publish in either calendar |
| 13 | Default stack if the repository is empty | PostgreSQL (the handoff's types imply it); Python 3.12 with typed code, pytest, and SQL migrations. Record an ADR if you pick otherwise | Native exact decimals and strong parsing tools; the handoff fixes none |
| 14 | Status vocabularies | Register mapping_status is the discovery stage; the handoff verification_status (unverified, provisional, verified, blocked) is the publish gate. A source is verified only when every in-scope mapping row is VERIFIED | Joins the two vocabularies without losing either |
| 15 | Oromia and Awash POST endpoints | Obtain the nonce from the official page at run time and never store it. Treat both as lowest priority | A stored nonce goes stale and the endpoints are fragile |
| 16 | CBE `_limit` parameter | Investigate first. Do not set it until its effect on the returned records is known | It may silently truncate results |
| 17 | National Bank of Ethiopia reference rate | Investigate whether an official publication exists and record the finding. Add it as an indicative_reference source only if it is a public official feed | The handoff keeps that category without naming a source |
| 18 | Register entry for Addis | Update to partially_verified, citing the 2026-10-10 capture | The capture shows structure but no comparison with the official display |
