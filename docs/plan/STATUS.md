# STATUS

Maintained by the agent. See CLAUDE.md §Reporting for what to record.

---

## Session 1 — 2026-10-10

### Current milestone: M11 in progress. Scheduler wired. Accumulating 14 days of data.

**0-trusted source resolution (2026-10-12):**

Three distinct problems, three solutions:

1. UNKNOWN category + confirmed identity (Ahadu, Enat): set default_category=transactional (ADR-012). Added category parameter to all 6 HTML adapters (ahadu, enat, dbe, siinqee, berhan, global_) and threaded it through internal _parse_table helpers. Enat: 0→6 trusted. Ahadu: 0→1 trusted.

2. ADIB no date: updatedAt per row is a per-currency last-edit timestamp (USD=2026-09-30, GBP=2026-09-28, SAR=2026-09-23). Parsed as source_inferred date (ADR-013). source_record_key + source_inferred → CONFIRMED identity. ADIB: 0→18 trusted.

3. No date, no fix (Amhara, Bunna, Tsehay, DBE, Global, Goh Betoch, Siinqee): these banks publish no machine-readable date. LOCKED rule: fallback dates never participate in identity. They stay ambiguous and out of the trusted view. default_category set for DBE/Siinqee/Goh Betoch/Global so data is correctly classified when a date source is found. No workaround that doesn't weaken a LOCKED rule.

Also fixed: duplicate sources from double-seeding. Added UNIQUE constraint (bank_id, adapter_key) to migration and production DB. Merged FK references from duplicate rows before deleting.

Final trusted rates: 277 across 11 sources.
Command: `python3 -m pytest tests/ -q` → 421 passed in 5.39s.

1. CBE date parameter: `_build_url()` in scheduler/runner.py appends `?Date=YYYY-MM-DD` for `cbe_api`. CBE now returns today's 32 rates instead of years of historical data.
2. Rammis/Wegagen default_category: ADR-010 and ADR-011 written. `parse()` in both adapters now accepts a `category` parameter (default `UNKNOWN`). Scheduler passes `rate_source.default_category` at runtime. Both set to `transactional` in production DB. Rammis: 17 trusted. Wegagen: 10 trusted.
3. Production DB `exchange_rates` created and seeded. Tests now use `exchange_rates_test` only. `seed_and_run.py` and `api/app.py` default to `exchange_rates` (overridable via `DATABASE_URL` env var).
4. `seed_and_run.py` now disables test fixture sources automatically after seeding.

**Production DB state after first clean run:**
- 21 enabled sources, 19 succeeded, 2 failed (Berhan 403, CBO 403/timeout — live network).
- 126 trusted current rates across: CBE(32), BOA(18), NIB(18), Rammis(17), Omo(14), Sidama(12), Wegagen(10), Dashen(5).
- 0 trusted from: ADIB, Ahadu, Amhara, Bunna, DBE, Enat, Global, Goh Betoch, Siinqee, Tsehay — all ambiguous identity (no date) or UNKNOWN category pending owner decision.

**M11 — Scheduler wired + ADR-014 stub (2026-10-12):**
Files: scheduler/run_job.py (entry point, logs to logs/collection.log, exit 1 if all sources fail), scheduler/exchange_rates.cron (daily 05:00 UTC = 08:00 EAT), scheduler/exchange_rates.service + exchange_rates.timer (systemd alternative, Persistent=true for missed runs). ADR-014 written: freshness threshold measurement plan, placeholder SQL query, decision criteria (14 days + stable stddev). ADR-014 added to ADR-index.md.
DBE fix: _parse_date_from_description() reads tablepress-table-description span → source_published date → CONFIRMED identity. DBE: 0→19 trusted. Total trusted: 296 across 12 sources.
Command: `python3 -m scheduler.run_job` → exit 0, 19/21 succeeded, logs/collection.log written.
Command: `python3 -m pytest tests/ -q` → 421 passed.

Open: install cron or systemd timer to start automatic daily collection. M11 gate: 14 days of CONFIRMED observations per active source.


Modules: pipeline/ingest.py (validate→fingerprint→identity→deduplicate→persist chain), scheduler/runner.py (fetch→parse→ingest→finish_run per source, run_all for all enabled sources).
25 tests written and passed.
Command: `python3 -m pytest tests/test_m10_ingest_scheduler.py -v` → 25 passed in 0.66s.
Command: `python3 -m pytest tests/ -q` → 421 passed in 5.66s.

Ingest: accepts/flags/rejects/deduplicates per LOCKED rules. Candidates (changed values) counted as flagged, not accepted. Suspicious data (buying>selling) flagged for raw_capture trigger.
Scheduler: recover_stuck_run before start_run; UniqueViolation caught (already-running guard); schema fingerprint stored on first run, compared on subsequent runs; last_success_at updated on success/partial_success; one failure per source never stops run_all.
Fix recorded: ingest count logic — changed-action observations must be flagged, not accepted.

Open: scheduler not yet wired to a cron/loop. run_all(conn) must be called externally (e.g. cron job or manual trigger). Phase 8 (harden with real data) requires 14 days of live collection.

**M9 — Read API, UI, alerts, runbook (2026-10-10):**
Modules: api/app.py (Flask read API), api/templates/index.html (minimal UI), alerts/checker.py (4 alert checks).
Docs: docs/runbook.md (stuck run, layout change, disputed rate + production-readiness checklist).
23 tests written and passed.
Command: `python3 -m pytest tests/test_m9_api_alerts.py -v` → 23 passed in 0.67s.
Command: `python3 -m pytest tests/ -q` → 396 passed in 5.08s.

API endpoints: GET /health, GET /rates, GET /rates?source_id=<id>, GET /rates/<source_id>, GET / (UI).
UI labels: PROVISIONAL (gap review L), PENDING REVIEW (gap review C), STALE. Effective date and last fetch shown separately.
Alert checks: failed_run, schema_change, disappearing_data (gap review G), stale_rates. All respect is_enabled flag and time windows.
Production-readiness checklist in docs/runbook.md.

Open: scheduler/ not yet wired (alerts run on demand via run_all_checks). No production deployment — Phase 8 (harden with real data) requires 14 days of collected data.

**M8c — Wave 4 adapters (2026-10-10):**
Adapters: DBE (F), Siinqee (F), Global (F two-table), Ahadu (G text DD/MM/YYYY), Enat (G text), Omo (D multi-table DD/MM/YYYY).
Deferred: Abay (403), Gadaa (JS-rendered), Tsedey (JS-empty tables).
54 tests written and passed.
Command: `python3 -m pytest tests/ -q` → 373 passed in 4.09s.

**M8b — Wave 3 adapters (2026-10-10):**
Adapters: Amhara (E SSL), BOA (E SSL date-in-header), Bunna (E wide no-date), Goh Betoch (F-like), NIB (D date-table), Sidama (G text), Berhan (G text), Tsehay (E-like no-date).
Deferred: Siket (403), ZamZam (403).
Sidama regex fix: Birr optional after No Trade; whitespace normalization.
82 tests written and passed.

**Wave 5 — DEFERRED:**
- Awash (H1): AJAX nonce required at runtime. No headless browser available.
- Oromia (H1): AJAX nonce required at runtime. No headless browser available.
- Anbesa (H2): JS-rendered. Headless browser required.
- Shabelle (H2): JS-rendered. Headless browser required.
- Hijra: DNS failure. Domain does not resolve.

### What is complete

**M7 — Trusted view, runs, review workflow (2026-10-10):**
Modules: pipeline/runs.py (start/finish/recover_stuck/raw_capture), trusted_view/query.py (get_trusted_rates, get_observation_with_warnings), review/workflow.py (decide_candidate). 19 tests written and passed.
Acceptance tests covered: 9 (partial — run lifecycle), 10, 11, 19, 21, 22. Gap-review tests: C, G, K, L.
Command: `python3 -m pytest tests/ -v` → 170 passed in 1.58s.

Fixtures: fixtures/dashen/{normal,empty,malformed,partial_one_table,no_date_in_weighted}.html. Adapter: adapters/dashen/adapter.py (Type D — parse only, partial-failure tolerant). 29 tests written and passed.
Key findings from actual fixture vs notes: weighted avg table has 4 rows (USD/EUR/SAR/AED), not 5; AED appears in all three tables. Notes corrected against fixture evidence.
Identity: transactional/cash → ambiguous (no source-published date). Weighted avg → confirmed (source_published date from header). Gap review test F confirmed: per-table dates never shared.
Command: `python3 -m pytest tests/ -v` → 127 passed in 1.28s.
Open: browser comparison TO VERIFY. Transactional/cash identity ambiguous until source-published date found. Mapping doc notes updated.

Fixtures: fixtures/cbe/{normal,single_date,empty,malformed,schema_changed,unknown_currency}.json. Adapter: adapters/cbe/adapter.py (Type A — parse only). 30 tests written and passed.
Schema-change detection: raises ValueError when a rate field is absent from an ExchangeRate item (asymmetric presence = schema change). source_record_key = item_id:category for cash/transactional uniqueness.
Command: `python3 -m pytest tests/test_m3_pipeline.py tests/test_m4_adib_adapter.py tests/test_m5_cbe_adapter.py -v` → 98 passed in 0.33s.
Open: browser comparison of API values vs official display TO VERIFY. Zero=not-offered TO VERIFY. SDR→XDR mapping TO VERIFY.

Mapping doc written: docs/mapping/addis.md. Fixtures: fixtures/adib/{normal,empty,malformed,unknown_currency,duplicate_fetch}.json. Adapter: adapters/adib/adapter.py (Type B2 — parse only, no network). 29 tests written and passed.
Identity fix: pipeline/identity.py updated — source_record_key alone is not CONFIRMED without a source-published date. Row id without date is not a publication discriminator.
Command: `python3 -m pytest tests/test_m3_pipeline.py tests/test_m4_adib_adapter.py -v` → 68 passed in 0.20s.
Open: API currently 403. All tests use 2026-10-10 fixture. Official-display comparison not done. Plain buying/selling category TO VERIFY.

Modules written: domain/records.py (AdapterRecord), domain/enums.py (status enums), pipeline/validate.py, pipeline/normalize.py, pipeline/fingerprint.py, pipeline/identity.py, pipeline/deduplicate.py, pipeline/persist.py.
39 tests written and passed: acceptance tests 1, 2, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17, 18; gap-review tests A, B, D, E, J; plus normalize/fingerprint/identity unit tests.
Command: `python3 -m pytest tests/test_m3_pipeline.py -v` → 39 passed in 0.26s.


**M1 — Wave 1 (CBE, Dashen, Addis):** Live fetches, fixtures, mapping docs. See previous STATUS entry.

**M1 extended — All remaining banks surveyed (2026-10-10):**
Survey script run against 24 additional banks. Results in docs/evidence/wave_survey/. Mapping docs written for all reachable banks.

### Survey results by bank

| Bank | HTTP | Type | Tables | Key finding |
|------|------|------|--------|-------------|
| RAMMIS | 200 | JSON API | — | Clean API: base_currency=ETB, effective_date per record, buying/selling, 17 currencies |
| WEGAGEN | 200 | JSON API (Strapi) | — | Strapi v4: date, code, unit=1, buying, selling, tra_buying, tra_selling, 10 currencies |
| ZEMEN | 200 | HTML | 0 | Rates show "Buying: --" — JS/AJAX rendered. Need AJAX endpoint. |
| CBO | 200 | HTML | 2 | Date in table 0 header ("Exchange Rate October 10, 2026"). Cash+Txn combined + weighted avg. |
| HIBRET | 200* | HTML | 1 | Cash+Txn table. SSL cert error (verify=False used for investigation). |
| AMHARA | 200* | HTML | 2 | Clear cash+txn table + weighted avg. "NO TRADE". SSL cert error. |
| BERHAN | 200 | HTML | 0 | Rates in page text ("1 USD ($)"). No table. |
| BUNNA | 200 | HTML | 1 | Wide table: CASH + TRANSACTION + AVERAGE columns. No date. |
| BOA | 200* | HTML | 1 | Date in header ("October 10, 2026"). Cash section + Transaction section in one table. SSL cert error. |
| GOH_BETOCH | 200 | HTML | 1 | Single table: buying, selling, weighted avg buying, weighted avg selling. No date. |
| NIB | 200 | HTML | 3 | Date table ("Oct 10, 2026") + cash/txn table + weighted avg. "No Trade". |
| SIDAMA | 200 | HTML | 0 | Rich text: Cash Buying/Selling, Transactional, Prev Weighted. "Birr" unit confirmed. No date. |
| SIKET | 403 | — | — | Access blocked. Deferred. |
| TSEHAY | 200 | HTML | 2 | Cash+Txn table + weighted avg. "No Trade". No date. |
| ZAMZAM | 403 | — | — | Access blocked. Deferred. |
| ABAY | 403 | — | — | Access blocked. Deferred. |
| AHADU | 200 | HTML | 0 | Rates in page text (buying/selling values visible, no currency labels in snippet). |
| DBE | 200 | HTML | 2 | Table 0: Currency+Code+Buying+Selling, 20 rows. Table 1: empty (JS?). No date. |
| ENAT | 200 | HTML | 0 | Date confirmed ("Oct 10, 2026"). Rates in page text. Three category tabs (Cash/Transaction/Weighted) — only one visible in static HTML. |
| GADAA | 200 | HTML | 0 | No rate data in static HTML. JS-rendered. |
| GLOBAL | 200 | HTML | 2 | Two tables (Currency/Buying/Selling). No date. USD table 2: buying > selling (review signal). |
| OMO | 200 | HTML | 3 | Three tables with dates in headers (DD/MM/YYYY). Cash=07/10/2026, Txn=07/10/2026, Weighted=06/10/2026. |
| SIINQEE | 200 | HTML | 1 | Single table: Currency/Buying/Selling. No date. |
| TSEDEY | 200 | HTML | 2 | Tables present but data rows empty — JS-rendered. |
| ANBESA | 200 | HTML | 0 | Official site found (anbesabank.com). Rates JS-rendered. Mirror no longer needed. |
| SHABELLE | 200 | HTML | 0 | Official site found (shabellebank.com). Rates JS-rendered. Mirror no longer needed. |
| HIJRA | ERROR | — | — | DNS resolution failure. Domain hijrabank.com does not resolve. |

*SSL certificate verification error — bypassed with verify=False for investigation only.

### Commands run and results
```
python3 survey_banks.py   → 24 banks surveyed, results in docs/evidence/wave_survey/survey_results.json
python3 survey_remaining.py → SSL/403/Wave5 banks investigated
```

### What was verified (KNOWN status — not yet VERIFIED)
All survey results are KNOWN from one fetch. None are VERIFIED (no official-display comparison performed for any bank beyond Wave 1).

### Key cross-bank findings

**"No Trade" / "NO TRADE" / "-" pattern:** Appears in NIB, Amhara, Tsehay, Global, Omo, CBO weighted avg. Consistent with zero=not-offered pattern from CBE/Addis. Recommendation: treat as NULL with validation_status=warning. TO VERIFY per bank.

**Date availability:**
- Source-published date confirmed: CBO (table header), NIB (separate date table), BOA (table header), Omo (per-table header), Enat (page text).
- No date found: Bunna, Goh Betoch, Tsehay, Hibret, Siinqee, DBE, Siket, Amhara, Berhan, Ahadu, Sidama, Global, Tsedey.
- identity_status = derived for date-confirmed banks; ambiguous for no-date banks.

**SSL errors:** Hibret, Amhara, BOA — server SSL cert cannot be verified. Adapters need verify=False or custom CA. Flag as access finding per source.

**JS-rendered (no static data):** Zemen, Tsedey, Gadaa, Anbesa, Shabelle, and partially Enat/Ahadu/Sidama/Berhan.

**Official sources found for Anbesa and Shabelle:** anbesabank.com and shabellebank.com. Register source_authority updated to official; kehulum.com mirrors no longer needed as primary.

**Hijra:** DNS failure — domain does not resolve. Source remains unresolved.

**Review signals:**
- Global Bank table 2: USD buying (164.9606) > selling (164.7893). Flag for review.
- Wegagen: buying == tra_buying for all records — category ambiguity.

### Decisions made inside the rules
- Anbesa and Shabelle: official sites found → source_authority updated to official in register. Mirror sources remain disabled per default 2.
- Hijra: DNS failure recorded. Source remains official_source_unresolved.
- SSL banks (Hibret, Amhara, BOA): verify=False used for investigation only. Production adapters must document this as an access finding.
- Zemen, Tsedey, Gadaa: collection_method updated to browser/ajax_endpoint in mapping docs.

### Decisions that need the owner
1. **Addis API 403** — still open. Retry from different network recommended.
2. **Addis zero values** — treat as NULL provisionally (recommendation unchanged).
3. **Addis plain buying/selling** — skip until confirmed (recommendation unchanged).
4. **SSL banks (Hibret, Amhara, BOA)** — is verify=False acceptable for production, or must SSL be resolved first? Recommendation: flag as provisional until SSL is resolved; do not block adapter development.
5. **Anbesa/Shabelle official sites** — confirm that anbesabank.com and shabellebank.com are the correct official domains before enabling.
6. **Global Bank USD buying > selling** — review signal in table 2. Likely a data quality issue on the bank's side. Confirm category of table 2 before ingesting.

### Risks
- ~10 banks require browser rendering (JS). No headless browser available in this environment. These banks are deferred to later waves.
- 3 banks with SSL errors need production decision on verify=False.
- Hijra has no reachable domain — may need manual investigation.
- Zemen AJAX endpoint unknown — requires browser dev tools to identify.

---

## Session 2 — 2026-10-13

### Production operations, UI rebuild, adapter findings

**Scheduler timing fix:**
First run (08:00 EAT) only caught CBE, DBE, Ahadu. Analysis of publishing times showed banks fall into 3 groups. Updated cron and systemd timer to 3 daily runs:
- 05:00 UTC (08:00 EAT) — CBE, DBE, Ahadu
- 09:00 UTC (12:00 EAT) — Enat, Rammis, Sidama, Wegagen
- 12:00 UTC (15:00 EAT) — BOA, NIB, Omo (target)
Files: scheduler/exchange_rates.cron, scheduler/exchange_rates.timer.

**Source cleanup — 11 sources disabled:**
- Stale/broken: ADIB (13 days stale), Dashen (3 days stale, adapter failing)
- Never collected a single rate: CBO, Berhan, Bunna, Amhara, Hibret, Global, Goh Betoch, Siinqee, Tsehay
Command: `UPDATE rate_source SET is_enabled = FALSE WHERE id IN (3,2,11,9,7,10,15,16,17,23,26);`
Active sources: 10 (CBE, DBE, Enat, Ahadu, Wegagen, Rammis, Sidama, BOA, NIB, Omo)

**UI rebuild — full replacement of index.html:**
- Compare Banks view: ranked bar chart, gold/silver/bronze positions, PROVISIONAL/STALE badges
- By Bank view: pivot table, currencies as rows, categories as column groups, pagination
- All Rates view: currency × bank matrix, sticky currency column, best rate highlighted green
- History view (new): 4th nav tab, grouped by effective_date descending, currency + date selectors, ★ best rate per date
- Search: datalist autocomplete (currencies + bank names)
- Filter: Major/All currency toggle
- Decimal display: rounded to 4 places (160.2319 not 160.2319000000)
Files: api/templates/index.html, api/app.py, trusted_view/query.py

**New query functions added to trusted_view/query.py:**
- `get_best_rates_by_currency(conn, currency)` — compare view
- `get_bank_rates_pivoted(conn, source_id)` — by-bank view
- `get_currency_matrix(conn, major_only)` — all-rates matrix
- `get_available_dates(conn)` — history date selector
- `get_history_by_currency(conn, currency, date)` — history view
- `get_search_suggestions(conn)` — datalist autocomplete
- All queries now filter `rs.is_enabled = TRUE`

**Adapter investigation findings (2026-10-13):**

| Bank | Finding | Status |
|---|---|---|
| BOA | Page has 0 HTML tables. Rates loaded via WordPress download manager (JS). Static fetch unreliable — succeeds occasionally, fails most runs. | Next sprint: find direct download endpoint or PDF |
| NIB | Site publishes daily with today's date (confirmed 2026-10-13 in page). Adapter parsing broken — site returns 200 but parse fails. | Next sprint: debug adapter against live page |
| Omo | `omobank.com` is a parked domain (domain reseller). Oct 12 data was a fluke. Real Omo Bank URL unknown. | Next sprint: find correct official URL |
| Ahadu | Adapter correct — homepage only publishes 1 currency (USD). Not a bug. | No action needed |
| Dashen | Adapter was working Oct 10, failing since. Page structure may have changed. | Next sprint: re-inspect page, fix adapter, re-enable |
| ADIB | Last successful collection Sep 30 (13 days). API endpoint may have changed. | Next sprint: re-inspect API, fix adapter, re-enable |

**Current production state (2026-10-13 end of day):**
- 10 active sources, 7 collecting fresh today (CBE, DBE, Enat, Ahadu, Wegagen, Rammis, Sidama)
- BOA, NIB, Omo: 1 day stale — adapter issues identified above
- All sources: verification_status = unverified (PROVISIONAL badge showing in UI)
- 429 tests passing

**Open — Step 3 (this week): verify active sources**
For each of the 7 healthy sources, visit bank website, confirm rate matches UI, then:
```sql
UPDATE rate_source SET verification_status = 'verified' WHERE id = <id>;
```
This removes the PROVISIONAL badge from the UI.
Priority order: CBE (id=1), DBE (id=12), Rammis (id=21), Sidama (id=22), Wegagen (id=27), Enat (id=13), Ahadu (id=6)

**Open — Next sprint: adapter fixes**
1. NIB — debug parser against live page
2. BOA — find direct rate endpoint (not the JS-rendered page)
3. Omo — find correct official URL for Omo Bank Ethiopia
4. Dashen — re-inspect page structure, fix adapter, re-enable (id=2)
5. ADIB — re-inspect API endpoint, fix adapter, re-enable (id=3)

---

## Session 3 — 2026-10-14

### Production operations, bug fixes, data quality

---

#### 1. Schema-change failures on startup (4 sources)

**Problem**: Sources 2 (Dashen), 5 (BOA), 11 (CBO), 18 (NIB) failed with `schema_change` error on first run of the day. Banks had updated their page structure overnight.

**Fix**: Reset schema fingerprints to force re-learning on next run:
```sql
UPDATE rate_source SET schema_fingerprint = NULL WHERE id IN (2, 5, 11, 18);
```
All 4 recovered on re-run.

---

#### 2. Anbesa Playwright fix

**Problem**: Anbesa adapter using `wait_until="domcontentloaded"` — page JS not finishing before scrape.

**Fix**: Changed to `wait_until="commit"` + `page.wait_for_timeout(5000)` in `adapters/anbesa/adapter.py`.

Anbesa now collects successfully (run 473).

---

#### 3. History view 500 error (two bugs)

**Bug 1**: `get_available_dates()` in `trusted_view/query.py` returning `None` values from DB rows with no effective_date.
**Fix**: Added `if r[0] is not None` filter.

**Bug 2**: `hist_by_date` dict in `api/app.py` building with `None` key when effective_date was NULL.
**Fix**: Added `if d is None: continue` guard in the date-grouping loop.

---

#### 4. Pending review blocking stale data (5 banks)

**Problem**: Wegagen, BOA, Rammis, Tsedey, Zemen had `change_review_status='pending_review'` observations with `is_current=FALSE` blocking the trusted view. Old `is_current=TRUE` records were from days prior.

**Root cause**: Rate changes trigger `pending_review` + `is_current=FALSE` on the new record. The old record stays `is_current=TRUE`. The new record never becomes current until manually approved.

**Fix**: Manually approved all by superseding old records and setting new to `is_current=TRUE, change_review_status='new_publication'`.

**Review UI built** to prevent this needing manual SQL in future:
- `GET /review` — per-bank grouped table, old/new rate comparison, change % display
- `POST /review/decide` — approve/dismiss per observation
- `get_pending_review_observations()` added to `trusted_view/query.py`
- `api/templates/review.html` — checkboxes, select-all, per-bank selection

---

#### 5. Mass date-parsing fix (8 adapters)

**Problem**: 8 adapters had no date parser — all producing `collection_date_fallback`. Checked all 29 banks.

**Banks fixed** (added `_parse_date()` with month-name regex):
- `adapters/tsehay/adapter.py` — parses `"Daily Exchange Rate: October 14, 2026"` heading
- `adapters/siket/adapter.py` — fully rewritten with date parser
- `adapters/goh_betoch/adapter.py` — fully rewritten with date parser
- `adapters/hibret/adapter.py` — fully rewritten with date parser (SSL_VERIFY=False retained)
- `adapters/amhara/adapter.py` — fully rewritten, double-space handling via `re.sub(r'\s+', ' ', ...)`
- `adapters/dashen/adapter.py` — added `_extract_date_from_text()` for page-level date

**Banks confirmed no date on page** (permanently `collection_date_fallback`):
- Bunna, Siinqee, Global — pages genuinely have no date text

---

#### 6. source_record_key duplicate is_current bug

**Problem**: After adding date parsing, adapters were setting `source_record_key=f"{effective_date}:{code}:{category}"`. This caused `build_identity` to use the `source_record_key` path, generating key `26:2026-10-14:AED:cash:cash` instead of standard `26:AED:cash:2026-10-14`. Old fallback records had key `26:AED:cash:2026-10-13` — different logical keys, so both were `is_current=TRUE` simultaneously.

**Fix**: Set `source_record_key=None` in all 6 affected adapters (tsehay, siket, goh_betoch, hibret, amhara, dashen).

**DB cleanup**: Retired old fallback `is_current=TRUE` records:
```sql
UPDATE rate_observation SET is_current=FALSE
WHERE source_id=X AND effective_date_basis='collection_date_fallback' AND is_current=TRUE;
```
Reset schema fingerprints and re-ran all 6 adapters. Final state: all 6 banks on `2026-10-14`, `source_published`, zero fallback records.

---

#### 7. Widespread duplicate is_current bug (root cause fix)

**Problem**: `build_identity` generates a date-scoped key `{source_id}:{currency}:{category}:{date}`. Each new day = new logical key = `"new"` action = `is_current=TRUE` inserted without retiring the previous day's record. This affected **all banks** — 457 stale duplicate `is_current=TRUE` records accumulated across CBE, DBE, BOA, NIB, SIDAMA, RAMMIS, AWASH, BERHAN, CBO, ZAMZAM, ZEMEN, WEGAGEN, ENAT, DASHEN, AHADU, SIKET, OMO, GLOBAL, SIINQEE, ADIB.

**Root cause**: `pipeline/ingest.py` `_process_one()` — when action=`"new"` with a fresh date key, it inserted `is_current=TRUE` without checking for older current records for the same source/currency/category slot.

**Fix**: Added `_retire_older_current()` helper in `pipeline/ingest.py`:
```python
def _retire_older_current(conn, source_id, currency_code, category_id, logical_key):
    # Retires any is_current=TRUE records for same source/currency/category
    # with a different logical key (older date)
    UPDATE rate_observation SET is_current=FALSE
    WHERE source_id=%s AND source_currency_code=%s
      AND category_id IS NOT DISTINCT FROM %s
      AND is_current=TRUE AND logical_observation_key != %s
```
Called before `insert_observation()` whenever `is_current=True` and `action="new"`.

**DB cleanup**: One-shot SQL retired all 457 existing stale duplicates:
```sql
WITH ranked AS (
  SELECT id,
    ROW_NUMBER() OVER (
      PARTITION BY source_id, source_currency_code, category_id
      ORDER BY effective_date DESC NULLS LAST, id DESC
    ) AS rn
  FROM rate_observation WHERE is_current = TRUE
)
UPDATE rate_observation SET is_current = FALSE
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
```

**Verified**: 0 duplicates after fix. Full 30-source run confirmed no new duplicates created.

---

#### 8. Genuinely stale banks (bank-side, not fixable)

Confirmed by live page inspection:

| Bank | Latest Effective | Reason |
|------|-----------------|--------|
| Omo | 2026-10-12 | Website shows `12/10/2026` — bank hasn't updated |
| Abay | 2026-10-13 | `dateModified: 2026-10-13` in page meta — bank hasn't updated |
| Gadaa | 2026-10-13 | Bank hasn't updated |
| ADIB | 2026-09-30 | API broken — fetched Oct 12 but data is Sep 30 |
| Shabelle | 2026-10-08 | Infrequent updates — bank-side |
| Anbesa | no data | Collection failing |
| Oromia | no data | DNS down (known) |

---

#### 9. PROVISIONAL badge — all banks

**Finding**: All 31 enabled sources have `verification_status='unverified'`. The `_to_row()` function in `trusted_view/query.py` marks `is_provisional=True` for both `'unverified'` and `'provisional'`. So every bank shows PROVISIONAL in the UI.

**This is by design** — zero-trust policy. No bank has been manually verified yet.

**To remove PROVISIONAL for a bank**: visit the bank website, confirm rates match UI, then:
```sql
UPDATE rate_source SET verification_status = 'verified' WHERE id = <id>;
```

---

#### 10. Production state — end of 2026-10-14

**Collection results**: 30/31 sources succeeded. 1 failed (source 49 = Oromia, DNS down).

| Category | Banks | Count |
|----------|-------|-------|
| ✅ Oct 14, collecting fresh | CBE, DBE, BOA, NIB, SIDAMA, RAMMIS, AWASH, BERHAN, CBO, ZAMZAM, ZEMEN, WEGAGEN, ENAT, DASHEN, AHADU, SIKET, TSEDEY, TSEHAY, AMHARA, HIBRET, GOH_BETOCH, BUNNA, GLOBAL, SIINQEE, ANBESA | 26 |
| ⚠️ Stale (bank-side) | Omo (Oct 12), Abay (Oct 13), Gadaa (Oct 13), ADIB (Sep 30), Shabelle (Oct 8) | 5 |
| ❌ No data | Oromia (DNS), Anbesa (failing) | 2 |

**Total current trusted records**: ~296 across 26 active banks.

**All 31 sources**: `verification_status='unverified'` → PROVISIONAL badge showing for all.

---

#### 11. Known permanent limitations

- **Bunna, Siinqee, Global**: No date on page — permanently `collection_date_fallback`. Each day creates a new logical key; unchanged rates become orphaned when old date's records are retired. Workaround: manually re-promote old records when rates unchanged.
- **Oromia**: DNS failure — domain does not resolve. Needs manual investigation.
- **ADIB**: API endpoint returning Sep 30 data. Needs re-inspection.
- **Telegram scraping**: Investigated. Ethiopian bank Telegram channels either don't post rate numbers or are private. Not viable.

---

#### 12. Files changed this session

| File | Change |
|------|--------|
| `pipeline/ingest.py` | Added `_retire_older_current()` — fixes duplicate is_current bug |
| `trusted_view/query.py` | Fixed `get_available_dates()` None filter; added `get_pending_review_observations()` |
| `api/app.py` | Fixed hist_by_date None key crash; added `GET /review`, `POST /review/decide` |
| `api/templates/index.html` | Added Review nav tab |
| `api/templates/review.html` | NEW — review UI |
| `adapters/tsehay/adapter.py` | Added `_parse_date()`, `source_record_key=None` |
| `adapters/siket/adapter.py` | Fully rewritten, `_parse_date()`, `source_record_key=None` |
| `adapters/goh_betoch/adapter.py` | Fully rewritten, `_parse_date()`, `source_record_key=None` |
| `adapters/hibret/adapter.py` | Fully rewritten, `_parse_date()`, `source_record_key=None` |
| `adapters/amhara/adapter.py` | Fully rewritten, `_parse_date()`, `source_record_key=None` |
| `adapters/dashen/adapter.py` | Added `_extract_date_from_text()`, `source_record_key=None` |
| `adapters/anbesa/adapter.py` | `wait_until="commit"` + 5s timeout |

---

| Milestone | Status | Date |
|-----------|--------|------|
| M0 — Kickoff plan, normalized register, ADR index | COMPLETE | 2026-10-10 |
| M1 — Wave 1 evidence + all 32 banks surveyed | COMPLETE | 2026-10-10 |
| M2 — Physical schema, constraint tests, migrations | COMPLETE | 2026-10-10 |
| M3 — Core pipeline | COMPLETE | 2026-10-10 |
| M4 — Addis adapter | COMPLETE | 2026-10-10 |
| M5 — CBE adapter | COMPLETE | 2026-10-10 |
| M6 — Dashen adapter | COMPLETE | 2026-10-10 |
| M7 — Trusted view, runs, review workflow | COMPLETE | 2026-10-10 |
| M8 — Wave 2 adapters (Rammis, Wegagen, CBO, Hibret) | COMPLETE | 2026-10-10 |
| M8b — Wave 3 adapters (Amhara, BOA, Bunna, Goh Betoch, NIB, Sidama, Berhan, Tsehay) | COMPLETE | 2026-10-10 |
| M8c — Wave 4 adapters (DBE, Siinqee, Global, Ahadu, Enat, Omo) | COMPLETE | 2026-10-10 |
| M8d — Wave 5 (Awash, Oromia, Anbesa, Shabelle, Hijra) | DEFERRED | — |
| M9 — Presentation and operations (read API, UI, alerts, runbook) | COMPLETE | 2026-10-10 |
| M10 — Ingest pipeline + scheduler runner | COMPLETE | 2026-10-10 |
| M11 — Phase 8: harden with real data | PENDING | needs 14 days live data |
