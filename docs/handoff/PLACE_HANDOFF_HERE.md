# Ethiopian Bank Exchange Rate Intelligence System
**Architecture, Canonical Data Contract, Persistence Rules, Testing, and Bank Mapping Handoff**
**Design handoff baseline — 2026-10-09**

> Portable design handoff. LOCKED means approved architecture; TO VERIFY means evidence is still required. No production code or live verification is claimed.

## 0. Purpose, phase, and status vocabulary
- **Purpose:** Consolidate the design decisions into a portable handoff so work can continue in a new chat without losing approved rules, test expectations, bank mappings, or unresolved verification items.
- **Phase:** Specification/design only. No production code, migrations, live source verification, or test execution is claimed by this document.
- **LOCKED / APPROVED:** Architectural decisions explicitly approved in the conversation. Treat as binding unless new evidence shows a concrete contradiction.
- **KNOWN:** Previously inventoried or discussed source structure; not necessarily re-tested during this session.
- **TO VERIFY:** Must remain unverified until actual bank responses/pages are inspected and compared with the bank’s official publication.
- **PROPOSED:** Recommended technical option that still needs final evidence/review before physical schema is frozen.

## 1. System purpose and architectural principles
- **Purpose:** Collect published exchange rates from Ethiopian banks, normalize them into a consistent data contract, preserve history and correction audit trails, and present trusted rates with explicit freshness and uncertainty information.
- **Core separation:** Bank = institution; Rate Source = a specific page/API/feed; Collection Run = one retrieval attempt; publication/snapshot identity = one observed source publication; Rate Observation = one currency/category rate within that publication; Observation Version = an immutable accepted version or confirmed correction.
- **Shared pipeline + adapters:** Bank-specific adapters interpret their own source. Shared logic handles normalization, validation, identity/deduplication, correction review, persistence, and diagnostics. Avoid bank-specific parsing conditions scattered through shared persistence logic.
- **History-first:** Never overwrite previous accepted history as a normal update. Preserve previous versions and link confirmed corrections to predecessors.
- **No guessing:** Do not invent effective dates, currency mappings, category meanings, buying/selling direction, stable IDs, or correction classifications. If evidence is insufficient, preserve the candidate and flag ambiguity.
- **Keep it practical:** No separate publication table is required for the initial implementation. Keep publication identity on run/observation records unless a concrete requirement justifies a new entity.
- **Raw response policy:** Retain raw responses conditionally for failed, malformed, or suspicious collections, not routinely for every successful valid response. Normalized observations and audit history are always retained.

## 2. Core entities and responsibilities
- **Bank:** Institution metadata: id, stable code, name, optional institution_type, is_active, created_at. Deactivation must not delete history.
- **Rate Source:** Specific endpoint/page/feed: id, bank_id, source_url, collection_method (api/html/browser), adapter_key, verification_status (unverified/provisional/verified/blocked), is_enabled, last_success_at, created_at. A bank may have multiple sources.
- **Rate Category:** Controlled registry: id, stable code, name, description, is_active, approved_at. Source labels map into canonical categories.
- **Collection Run:** One attempt, successful or not: id, source_id, started_at, finished_at, status (running/success/partial_success/failed), http_status, records_found/accepted/flagged, error_code, error_summary, duration_ms.
- **Rate Observation:** Normalized currency/category rate tied to source and collection run. Includes source currency, canonical currency when verified, category, rates, effective-date basis, fetched time, source/publication identity, fingerprint, validation/identity/review status, and version links.
- **Raw Capture:** Conditional evidence record: id, collection_run_id, captured_at, capture_reason (http_failure/parse_failure/schema_change/suspicious_data), content_hash, storage_reference, retention_until.
- **Publication table:** Not required for the first implementation. Publication identity remains in collection-run and observation fields for now.
- **Source configuration:** Recommended settings: identity_strategy, effective_date_policy, category_mapping_version, currency_mapping_version, optional schema_fingerprint, identity_review_required.

## 3. Controlled rate categories — approved baseline
- **Initial categories:** cash; transactional; weighted_average; indicative_reference.
- **Mapping rule:** Each adapter maps actual source labels/tables/fields to canonical categories. Cash and transactional rates for the same currency/date are distinct observations.
- **Extension rule:** Add a category only when the published rate has genuinely different business meaning. Spelling or label variations alone do not justify a new category.
- **Unknown category:** Flag it for review; never silently map an unknown heading/field to a familiar category or include it in trusted presentation before review.

## 4. Currency normalization contract
- **Separate source and canonical values:** Store canonical currency_code separately from source_currency_code and optional currency_name. Suggested canonical code type VARCHAR(3), only when verified.
- **Currency registry:** Maintain a controlled registry of canonical codes, names, and approved aliases.
- **Mapping rule:** Normalize only when the source code/label mapping is verified. Prefer verified codes over names as identity.
- **Unknown/ambiguous currency:** Do not guess. Flag it and exclude it from trusted current-rate presentation until resolved.
- **CBE known fields:** Previously inventoried fields include currency.CurrencyCode and currency.CurrencyName. The full response envelope and exact semantics remain TO VERIFY.
- **Open item:** Actual aliases and exceptional mappings are not yet finalized.

## 5. Canonical observation field contract
- **Relationships and identity:** id; source_id (required); collection_run_id (required for collected observations); category_id (required); currency_code (canonical when verified); source_currency_code; currency_name; source_record_key (nullable); source_publication_key (nullable); logical_observation_key (nullable if ambiguous); snapshot_fingerprint; version_number; supersedes_id.
- **Rate values:** buying_rate and selling_rate are independently nullable. Missing side is NULL, never zero. At least one side must be present for an ordinary rate observation. Supplied values must be positive to qualify as valid.
- **Effective date:** effective_date means the date the rate applies, not fetch date. It may be NULL when genuinely unknown. effective_date_basis values: source_published, source_inferred, collection_date_fallback, unknown. Never silently set today as the effective date just because source date is missing.
- **Timestamps:** fetched_at = retrieval time; created_at = persistence time. Store timestamps as timezone-aware TIMESTAMPTZ.
- **Validation status:** validation_status: validated, warning, rejected. validation_messages should be structured JSON/JSONB. Source verification, collection status, identity status, and observation validation are separate concepts.
- **Identity status:** identity_status: confirmed, derived, ambiguous. A structurally valid rate with ambiguous identity is not the same as malformed data.
- **Change review status:** change_review_status: not_required, pending_review, confirmed_correction, new_publication, mapping_issue, dismissed. Record decision reason, time, and responsible actor or automated rule.
- **Mapping provenance:** Track category_mapping_version and currency_mapping_version. Mapping/schema changes must be traceable to observations produced under earlier logic.
- **Original text:** Where useful, preserve original source rate text alongside normalized decimals for diagnosis without retaining every successful raw response.

## 6. Observation identity and deduplication — LOCKED
- **Identity hierarchy:** Use strongest available evidence: (1) genuinely stable source record ID; (2) explicit verified publication identity plus source/currency/category; (3) verified source-specific fallback based on documented publication behavior; (4) if still ambiguous, retain and flag rather than merge.
- **Conceptual key:** source + trustworthy publication identity + canonical currency + canonical category, with stable source_record_key/publication discriminator when available. Exact identity strategy is source-specific, not a universal assumption.
- **Fallback limitation:** Some sources lack stable IDs or trustworthy effective dates. Use a fallback only after source behavior is verified. If multiple publications may exist for the same currency/category/date, a stable discriminator or documented source-specific rule is needed.
- **Fingerprint:** Use a deterministic hash of normalized publication content and publication identity where available. Do not include fetched_at. Identical snapshots can be recognized; differing snapshots alone do not prove correction.
- **Same publication + same values:** Deduplicate. No duplicate business observation and no version increment just because the scheduler fetched the source again.
- **New publication:** Create a new logical observation when evidence establishes a distinct publication/effective period.
- **Changed values:** A changed number alone is not proof of correction. It could be a correction, new intraday publication, stale/changed page, or parser/mapping bug. Create a review candidate; do not overwrite or automatically call it a correction.
- **Ambiguous identity:** Keep candidate/diagnostics. Do not invent date/key, merge unsafely, force a key to satisfy uniqueness, or include it in trusted current-rate view.
- **Publication entity:** Do not introduce a separate publication table in the initial implementation.
- **Approved summary:** Source-specific publication identity with safe fallback; identical normalized snapshots deduplicated; changed values not automatically corrections; confirmed corrections create linked immutable versions; ambiguous identity flagged rather than guessed.

## 7. Correction lifecycle and current version — LOCKED
- **First accepted observation:** Create version 1 when identity is established and the observation is accepted into the committed version chain.
- **Repeated same publication/value:** No new version.
- **Possible changed value:** Keep a pending_review candidate. Do not assign a committed version number or make it current until classified.
- **Confirmed correction:** Create a new immutable version linked by supersedes_id to the previous version; record review evidence; switch current status atomically.
- **New publication:** Create a new logical observation, not a correction version of the older publication.
- **Mapping issue:** Preserve the original stored result and record the corrected interpretation. Do not mislabel a parser/normalization issue as a bank correction.
- **Dismissed candidate:** Keep audit/review record as appropriate and exclude it from trusted current-rate presentation.
- **Current version:** Do not select by greatest fetched_at alone. Respect explicit version chain/current status, compare effective dates, and apply freshness policy.
- **Atomic correction transaction:** Serialize competing corrections; verify same logical identity; insert next version with supersedes_id; mark predecessor non-current; mark new version current; commit. Roll back everything if any step fails.
- **Version integrity:** Version number positive; predecessor belongs to same logical observation; no cycles; unique (logical_observation_key, version_number) for identified keys; at most one current version per identified logical observation.
- **Separate dimensions:** Validation status, identity status, and change-review status must remain separate.

## 8. Database types and constraints
- **Proposed physical types:** Choose one ID convention consistently: BIGINT identity or UUID. Currency code VARCHAR(3) where verified. Rates PostgreSQL NUMERIC(24,10) proposed, pending source-value verification. Dates DATE. Times TIMESTAMPTZ. SHA-256 fingerprints CHAR(64) or VARCHAR(64). Diagnostics JSONB. URLs TEXT.
- **Precision status:** NUMERIC(24,10) is a proposal, not final. Inspect actual source values and ensure no source value is silently rounded/coerced. Preserve original rate text where useful.
- **Foreign keys:** Every observation references existing source, category, and collection run; every source references an existing bank.
- **Rate checks:** Every supplied buying/selling value > 0. At least one side non-NULL for an ordinary rate observation. Missing values remain NULL.
- **Version checks:** Committed version_number > 0; predecessor same logical identity; no cycles; unique logical key + version number when key is known.
- **Current-version constraint:** At most one current version per identified logical observation, using a partial unique index or equivalent. Switching versions must be atomic.
- **Ambiguous candidates:** logical_observation_key may be NULL for genuine ambiguity. Retain for review but exclude from current-rate view and identified-key uniqueness.
- **Controlled statuses:** Use CHECK constraints or database enums for allowed statuses.
- **Collection counters:** Counters default to 0 and remain consistent. A successful run with no new rates is still successful.
- **Failure isolation:** Collection failure must not delete or invalidate earlier observations. Run failure and individual record rejection are separate outcomes.
- **No silent coercion:** Never silently round an invalid decimal, coerce it to zero, or accept it as a valid rate.

## 9. Collection runs and raw evidence
- **Run statuses:** running, success, partial_success, failed.
- **Success semantics:** A run can succeed while finding no new observations. Source retrieval success and rate freshness are different.
- **Partial success:** Use when independent portions succeed while another fails, e.g. one Dashen table parses and another does not.
- **Diagnostics:** Record machine-readable error_code, human-readable error_summary, HTTP status where available, duration, counts, and source/run linkage.
- **Raw capture triggers:** http_failure, parse_failure, schema_change, suspicious_data. Normal valid successful responses need not be retained raw.
- **Raw protection:** Protect evidence, limit size, hash content, and apply a retention policy.
- **Open item:** Exact raw-evidence retention duration remains undecided.

## 10. Validation, freshness, and trusted display
- **Validation layers:** Structural; type/value; business plausibility; freshness; completeness; cross-check.
- **Structural failures:** Missing required currency/structure may reject the record or fail the run if the response cannot be interpreted at all.
- **Type/value failures:** Unparseable numeric text is rejected for that record and diagnosed; no silent coercion.
- **Business checks:** Zero/negative/unexpected values are flagged or rejected under explicit rules; never replaced with another value.
- **Freshness:** A page fetched today can display an old effective date. Show effective date and last fetch separately.
- **Completeness:** A previously present category/table disappearing triggers a warning for possible publication change or parser breakage.
- **Cross-check:** A large difference from a previous publication is a review signal, not automatic rejection or proof of correction.
- **Trusted current rate:** Exclude rejected observations and ambiguous identities. Use latest valid version of each logical observation, respect confirmed corrections, compare effective dates, apply source/category freshness policy, and show uncertainty warnings.
- **No silent fallback:** Never silently substitute an older rate for a missing current rate. If older data is displayed, label its effective date and staleness.
- **Freshness thresholds:** Not finalized. Configure by source/category where publication behavior differs; determine thresholds from evidence, not arbitrary hardcoding.
- **Warnings:** Warning-level observations may still be useful depending on warning type, but uncertainty must be visible.

## 11. Adapter mapping contract
- **Required adapter output:** Source identity; source record/publication identity if available; source currency value; canonical currency mapping and evidence; category mapping and evidence; buying/selling values with missing sides preserved; effective date and basis; mapping/schema versions; diagnostics for unknown/missing/malformed fields.
- **Shared pipeline responsibility:** Validate, normalize, fingerprint, deduplicate, route changed records to review, persist versions, record diagnostics, preserve history.
- **Adapter responsibility:** Interpret its bank’s page/API, labels, date semantics, category meaning, currency naming, rate direction, and identity capabilities.
- **Mapping specification fields:** Exact source field/table/selector; canonical target; transformation; evidence; VERIFIED or TO VERIFY status; date/currency/category rules; identity strategy; acceptance fixtures.
- **Provisional source rule:** A source may be enabled for controlled testing while provisional. Enabled does not mean verified. Unverified data must be visibly provisional.

## 12. First three bank mapping contracts
- **CBE — known inventory:** Source type: structured API. Previously inventoried fields: currency.CurrencyCode; currency.CurrencyName; cashBuying; cashSelling; transactionalBuying; transactionalSelling. Date filter known in form ?Date=YYYY-MM-DD.
- **CBE — mapping draft:** currency.CurrencyCode → source_currency_code, then canonical currency_code only after code mapping is verified. currency.CurrencyName → currency_name. cashBuying → buying_rate for category cash; cashSelling → selling_rate for cash. transactionalBuying → buying_rate for transactional; transactionalSelling → selling_rate for transactional. These are field-name-based proposals and remain TO VERIFY until compared with actual responses and official publication.
- **CBE — identity/date:** Candidate key: source + verified publication identity + canonical currency + canonical category. Verify response envelope, returned date meaning, multiple publications per requested date, and stable source record ID. The ?Date= parameter is a request filter, not proof that each returned record is effective on that date. Empty response is recorded; no fabricated rates or silent fallback.
- **CBE — TO VERIFY:** Exact response envelope/nesting; effective/publication-date semantics; multiple publications per date; stable record ID; currency-code validity; buying/selling meaning and values against official CBE display; empty/error behavior.
- **Dashen — known inventory:** Source type: webpage with separate transaction, cash, and weighted-average tables. Exact selectors, headings, currency labels, and date extraction are not verified.
- **Dashen — mapping draft:** Transaction table → transactional; cash table → cash; weighted-average table → weighted_average, only after actual headings and business meaning are confirmed. Map buying/selling columns from actual headers, not assumed visual position. Source currency label/code maps to canonical currency only when verified.
- **Dashen — identity/date:** Candidate key: source + verified table/category + publication identity + canonical currency. Parse each table independently. Preserve per-table dates if they differ. Do not apply a page-wide date to all tables unless evidence confirms it. Missing/malformed table is flagged; do not set values to zero or reuse another table.
- **Dashen — TO VERIFY:** Exact page/source; selectors; headings; currency labels; buying/selling direction; weighted-average meaning; per-table effective dates; whether dates are shared; partial-failure behavior; layout-change detection.
- **Addis International Bank — known inventory:** Previously identified endpoint: https://api.addisbanksc.com/api/exchange-rates. Described as structured API, but response schema and semantics are unverified.
- **Addis — mapping rule:** Do not copy CBE field names or assumptions. Do not assume categories, currency direction, publication date, stable IDs, or empty-response behavior from the endpoint name. Map only fields actually observed and compared with official publication.
- **Addis — identity/date:** Candidate key: source + verified publication identity + canonical currency + canonical category, if the response supports these concepts. If no stable ID/date exists, define fallback only after publication behavior is verified; otherwise flag ambiguous.
- **Addis — TO VERIFY:** HTTP behavior/response envelope; JSON field names/types; currency fields; buying/selling direction; categories; effective/publication date; stable record ID; multiple publications per date; empty/error behavior; values versus official publication.
- **Cross-bank rule:** Do not mark a field VERIFIED because the endpoint exists or a name looks self-explanatory. Keep evidence and comparison results. Unknown/changed fields and categories trigger warnings/review, not guesses.

## 13. Acceptance and testing contract
- **Identity tests:** 1) Same publication/value fetched twice → no duplicate observation/version. 2) Cash and transactional same currency/date → distinct observations. 3) Later verified effective date → new logical observation; old history unchanged. 4) Changed value same publication → pending review; prior version remains current. 5) Confirmed correction → exactly one new immutable version linked to predecessor.
- **Ambiguity tests:** 6) No trustworthy date/stable ID → candidate retained as ambiguous, no fabricated key/date, excluded from trusted current view. 7) Unknown category flagged, not silently mapped. 8) Unknown currency flagged, not guessed.
- **Collection robustness tests:** 9) Dashen cash table succeeds but transaction table fails → successful table handled independently, partial success diagnosed, no invented rates. 10) Timeout/unusable response → failed run recorded, prior observations remain available with their freshness unchanged. 11) Successful run with no new rates remains success.
- **Concurrency/version tests:** 12) Two workers correct same observation → no competing current versions. 13) Positive unique version numbers; predecessor same logical identity; no cycles. 14) At most one current version per identified logical observation.
- **Numeric/normalization tests:** 15) No silent rounding/coercion to zero. 16) Missing side remains NULL. 17) Source currency/rate text retained where configured. 18) Mapping version traceable.
- **Current/freshness tests:** 19) Current selection does not rely only on fetched_at. 20) Stale repeated page cannot replace a newer effective rate silently. 21) Stale rates show effective date/warning. 22) Older data is never silently substituted for missing current data.
- **Fixtures and evidence:** Each adapter needs representative fixtures for normal, empty, malformed/schema-changed, unknown currency/category, duplicate fetch, and applicable partial-failure cases. Compare normalized outputs against documented official bank publications. These are acceptance requirements, not tests already executed.

## 14. Locked decisions vs open decisions
- **LOCKED / APPROVED:** Overall separation of entities; controlled categories with approved extensions; conditional raw-response retention; shared pipeline + source-specific adapters; source-specific publication identity with safe fallback; identical normalized snapshots deduplicate; changed values are not automatically corrections; confirmed corrections create linked immutable versions; ambiguous identity is flagged rather than guessed; no separate publication table initially; immutable history; current-rate choice not based on fetch time alone.
- **PROPOSED / NOT FINAL:** Physical ID convention (BIGINT vs UUID); NUMERIC(24,10) precision/scale; exact CHECK/enum implementation; raw retention duration; freshness thresholds; final physical schema and source-specific identity indexes.
- **TO VERIFY — CBE:** Response envelope, date semantics, stable ID, multiple publications per date, official-value comparison.
- **TO VERIFY — Dashen:** Selectors, headings, table dates, currency labels, buying/selling columns, weighted-average meaning, partial parse behavior.
- **TO VERIFY — Addis International Bank:** Actual schema, rate direction, categories, date semantics, stable IDs, empty/error behavior.
- **Not done:** No production code; no migrations; no live verification claimed; no tests claimed as executed; no bank mapping marked verified without evidence.

## 15. Recommended next sequence
- **Step 1 — Verify source evidence:** Inspect actual CBE API responses, Dashen official webpage tables, and Addis International Bank API responses. Save representative fixtures and compare values with official publications. Record verification timestamp and evidence.
- **Step 2 — Complete mappings:** For each source field/table, document exact path/selector, canonical target, transformation, category/currency/date meaning, identity strategy, evidence, status, and tests.
- **Step 3 — Finalize physical schema:** After inspecting samples, lock precision/scale, ID convention, identity indexes, current-version constraints, candidate storage, retention, and status constraints.
- **Step 4 — Write adapter tests:** Build fixtures and acceptance tests before production scheduling. Verify deduplication, correction review, ambiguity handling, and failure isolation.
- **Step 5 — Implement only after approval:** Keep production code out of scope until specification and mapping evidence are reviewed and approved.

## 16. Reusable prompt for the next chat
- **Handoff prompt:** Continue the Ethiopian Bank Exchange Rate Intelligence System design from this handoff. Treat every LOCKED / APPROVED decision as binding; do not reopen it unless new evidence shows a concrete contradiction. The project is still in specification/design phase: do not write production code yet. First verify source evidence for CBE, Dashen Bank, and Addis International Bank, keeping every TO VERIFY label until evidence proves it. Produce per-bank mapping specifications with exact field/table/selector paths, canonical targets, transformations, date/currency/category semantics, identity strategy, evidence, and adapter acceptance fixtures. Then finalize physical database constraints and numeric precision from actual source values. Never invent mappings, publication dates, stable IDs, corrections, or source behavior. Keep the architecture practical and avoid adding a publication table unless a concrete requirement justifies it. Preserve immutable history; deduplicate identical normalized snapshots; treat changed values as review candidates rather than automatic corrections; use linked versions only for confirmed corrections; keep ambiguous candidates out of trusted current-rate presentation. The tests listed are acceptance requirements, not evidence that tests have already run.